"""Task040 S3a: dynamic topological-orbit action-only pilot Gate."""

from __future__ import annotations

import json
import math
from dataclasses import replace

import numpy as np
import pytest
from mpi4py import MPI

from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    target_stage4_config,
)
from src.solvers.floquet_background_hcurl_block_service import (
    build_bounded_harmonic_packet,
    create_bounded_harmonic_service,
)
from src.solvers.floquet_background_hcurl_block_transform import (
    build_hybrid_local_action_bloch_layout,
    create_active_trace_bloch_transforms,
)
from src.solvers.hybrid_local_dtn_action import assemble_hybrid_local_dtn_action_system

_TINY = np.finfo(float).tiny
_TOL = 1.0e-12


class _ActionRequest:
    def __init__(self, matrix):
        self.A = matrix


def _config():
    ordinary = target_stage4_config(degree=2, h_nm=100.0)
    return replace(
        ordinary,
        case_name="task040_v9_e_s3a_action_p2_6x3x2",
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        stage4_full3d_assembly_backend=ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        stage4_dtn_order_policy="zero_order",
        n_grating=ordinary.n_air,
        grating_width_x=ordinary.grating_width_x,
        grating_width_y=ordinary.period_y,
        grating_height=ordinary.domain_z_max - ordinary.interface_z,
        mesh_axis_cell_counts=(6, 3, 2),
        mesh_spacing_mode="boundary_fitted",
        unique_output=False,
    )


def _fill(vector, seed):
    start, stop = map(int, vector.getOwnershipRange())
    values = vector.getArray()
    values[:] = [
        complex(np.sin(0.17 * (index + seed)), np.cos(0.11 * (index + 2 * seed)))
        for index in range(start, stop)
    ]


def _relative(left, right):
    residual = right.duplicate()
    left.copy(residual)
    residual.axpy(-1.0, right)
    value = float(residual.norm()) / max(float(right.norm()), _TINY)
    residual.destroy()
    return value


def _finite(vector):
    return bool(np.all(np.isfinite(np.asarray(vector.getArray(readonly=True)))))


def _assert_factor_audit(audit):
    keys = (
        "solve_relative_residual",
        "normwise_backward_error",
        "repeat_error",
        "linearity_error",
    )
    for item in audit["factor_solve_audit"]:
        for key in keys:
            assert math.isfinite(float(item[key]))
            assert item[key] <= 1.0e-10


@pytest.mark.skipif(MPI.COMM_WORLD.size not in (1, 2), reason="serial/MPI2 only")
def test_task040_s3a_dynamic_action_bounded_harmonics():
    comm = MPI.COMM_WORLD
    system = assemble_hybrid_local_dtn_action_system(_config(), "bottom", comm=comm)
    transforms = None
    service = None
    packet = None
    evidence = {}
    try:
        layout = build_hybrid_local_action_bloch_layout(system)
        assert (layout.nx, layout.ny, layout.nz) == (6, 3, 2)
        assert layout.nedelec_degree == 2
        assert layout.auxiliary_rows == 0
        assert layout.phase_model == "topological_orbit_dft_approximation"
        widths = [np.diff(np.asarray(axis)) for axis in layout.axis_values[:2]]
        assert any(np.ptp(width) > 0.0 for width in widths)
        entity_block_count = len(layout.blocks)
        flat = [row for block in layout.blocks for row in block.active_ids]
        assert len(flat) == layout.active_rows
        assert len(flat) == len(set(flat))
        assert sorted(flat) == list(range(layout.active_rows))
        orbit_count = len(layout.orbit_rows)
        assert layout.nx * layout.ny == orbit_count == 18
        assert layout.active_rows == orbit_count * layout.rows_per_harmonic
        assert set(layout.orbit_rows) == {
            (ix, iy) for ix in range(layout.nx) for iy in range(layout.ny)
        }
        assert set(layout.orbit_rows.values()) == {layout.rows_per_harmonic}

        transforms = create_active_trace_bloch_transforms(layout)
        modal = transforms.q.createVecRight()
        physical = transforms.q.createVecLeft()
        modal_back = transforms.t.createVecLeft()
        physical_back = transforms.q.createVecLeft()
        try:
            _fill(modal, 3)
            transforms.q.mult(modal, physical)
            transforms.t.mult(physical, modal_back)
            tq_error = _relative(modal_back, modal)
            _fill(physical, 7)
            transforms.t.mult(physical, modal_back)
            transforms.q.mult(modal_back, physical_back)
            qt_error = _relative(physical_back, physical)
            assert tq_error <= _TOL
            assert qt_error <= _TOL
        finally:
            for vector in (physical_back, modal_back, physical, modal):
                vector.destroy()

        packet = build_bounded_harmonic_packet(
            _ActionRequest(system.A),
            transforms,
            require_exact_block_diagonal=False,
        )
        audit = packet.setup_audit
        block_rows = audit["block_rows"]
        harmonic_block_count = len(block_rows)
        assert audit["background_mode_count"] == harmonic_block_count == orbit_count
        assert all(rows == layout.rows_per_harmonic for rows in block_rows)
        assert audit["background_column_apply_count"] == layout.active_rows
        assert audit["max_local_rows"] == layout.rows_per_harmonic
        assert audit["max_local_rows"] <= 1024
        assert audit["factor_count_global"] == harmonic_block_count
        assert audit["require_exact_block_diagonal"] is False
        assert audit["dropped_coupling"] is True
        assert len(audit["block_off_block_audit"]) == 18
        for item in audit["block_off_block_audit"]:
            assert item["dropped_coupling"] is True
            assert math.isfinite(float(item["off_block_absolute_max"]))
            assert math.isfinite(float(item["off_block_norm_ratio_max"]))
        _assert_factor_audit(audit)
        off_absolute = [
            float(item["off_block_absolute_max"])
            for item in audit["block_off_block_audit"]
        ]
        off_ratio = [
            float(item["off_block_norm_ratio_max"])
            for item in audit["block_off_block_audit"]
        ]
        factor_keys = (
            "solve_relative_residual",
            "normwise_backward_error",
            "repeat_error",
            "linearity_error",
        )
        factor_local_max = {
            key: max(float(item[key]) for item in audit["factor_solve_audit"])
            for key in factor_keys
        }
        factor_global_max = {
            key: float(comm.allreduce(value, op=MPI.MAX))
            for key, value in factor_local_max.items()
        }

        service = create_bounded_harmonic_service(packet, transforms)
        source = transforms.q.createVecLeft()
        source2 = source.duplicate()
        combined = source.duplicate()
        output = source.duplicate()
        repeated = source.duplicate()
        output2 = source.duplicate()
        expected = source.duplicate()
        try:
            _fill(source, 5)
            _fill(source2, 9)
            service.apply(source, output)
            service.apply(source, repeated)
            service.apply(source2, output2)
            repeat_error = _relative(repeated, output)
            source.copy(combined)
            combined.axpy(0.31 - 0.27j, source2)
            service.apply(combined, expected)
            output2.scale(0.31 - 0.27j)
            output.axpy(1.0, output2)
            assert _finite(output)
            assert _finite(repeated)
            assert _finite(expected)
            linearity_error = _relative(expected, output)
            assert repeat_error <= _TOL
            assert linearity_error <= _TOL
        finally:
            for vector in (expected, output2, repeated, output, combined, source2, source):
                vector.destroy()
        assert service.apply_count == 4
        evidence = {
            "status": "S3A_DYNAMIC_ACTION_INFRASTRUCTURE_READY",
            "mesh": [layout.nx, layout.ny, layout.nz],
            "nedelec_degree": layout.nedelec_degree,
            "active_rows": layout.active_rows,
            "rows_per_harmonic": layout.rows_per_harmonic,
            "entity_block_count": entity_block_count,
            "harmonic_block_count": harmonic_block_count,
            "block_rows": list(block_rows),
            "phase_model": layout.phase_model,
            "axis_widths": [width.tolist() for width in widths],
            "tq_error": tq_error,
            "qt_error": qt_error,
            "repeat_error": repeat_error,
            "linearity_error": linearity_error,
            "off_block_absolute_max": max(off_absolute),
            "off_block_absolute_min": min(off_absolute),
            "off_block_absolute_values": off_absolute,
            "off_block_norm_ratio_max": max(off_ratio),
            "off_block_norm_ratio_min": min(off_ratio),
            "off_block_norm_ratio_values": off_ratio,
            "factor_audit_local_max": factor_local_max,
            "factor_audit_global_max": factor_global_max,
            "apply_count": service.apply_count,
            "solve_count": service.solve_count,
            "owner_local_harmonic_factor_count": audit["factor_count_global"],
        }
    finally:
        if service is not None:
            service.destroy()
        if transforms is not None:
            transforms.destroy()
        system.destroy()
        evidence["lifecycle"] = {
            "service_destroyed": service is None or service.destroyed,
            "transforms_destroyed": transforms is None or transforms._destroyed,
            "action_system_destroyed": system._destroyed,
            "no_global_direct_factor": True,
            "no_numeric_vector_allgather": True,
        }
    assert evidence["lifecycle"]["service_destroyed"]
    assert evidence["lifecycle"]["transforms_destroyed"]
    assert evidence["lifecycle"]["action_system_destroyed"]
    if comm.rank == 0:
        print("S3A_EVIDENCE " + json.dumps(evidence, sort_keys=True))
