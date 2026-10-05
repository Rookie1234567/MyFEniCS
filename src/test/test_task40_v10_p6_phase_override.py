"""Real small-mesh p6 Floquet phase override and carrier wiring checks."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.constraints.floquet_3d import build_double_floquet_mpc
from src.constraints.floquet_3d_high_order import build_high_order_constraint_data
from src.solvers import (
    dtn_boundary_phase_gauge,
    dtn_port_3d,
    fullspace_dtn_action,
    fullspace_physical_action,
    fullspace_same_mesh_hcurl_pmg_physical,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
    build_same_mesh_physical_action,
    destroy_same_mesh_physical_action,
)
from src.solvers.task40_v10_p6_yorbit import SCHEMA
from src.solvers.task40_v10_p6_periodic_profile import TASK40_V10_P6_PROFILE


INPUT = Path("input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat")


def _phase_rows(data, phases):
    phase_by_kind = {"x": phases[0], "y": phases[1], "corner": phases[0] * phases[1]}
    expected = {}
    for block in data.topology.blocks:
        for row, slave in enumerate(block.slave_global_dofs):
            raw = np.asarray(block.coefficient_transform[row], dtype=np.complex128)
            masters = np.asarray(block.master_global_dofs, dtype=np.int64)
            keep = np.abs(raw) > 1e-14
            expected[int(slave)] = (
                str(block.kind),
                masters[keep],
                phase_by_kind[str(block.kind)] * raw[keep],
            )
    kinds = set()
    for row, slave in enumerate(data.slave_global_dofs):
        kind, masters, values = expected[int(slave)]
        start, stop = map(int, data.offsets[row : row + 2])
        np.testing.assert_array_equal(data.master_global_dofs[start:stop], masters)
        np.testing.assert_allclose(data.coefficients[start:stop], values, rtol=0, atol=1e-14)
        kinds.add(kind)
    return kinds




def _assert_mpc_matches_constraint_data(mpc, data):
    coefficients, offsets = mpc.coefficients()
    masters = np.asarray(mpc.masters.array, dtype=np.int64)
    assert len(offsets) > int(np.max(data.slave_local_dofs))
    for row, slave in enumerate(data.slave_local_dofs):
        data_start, data_stop = map(int, data.offsets[row : row + 2])
        mpc_start, mpc_stop = map(int, offsets[int(slave) : int(slave) + 2])
        np.testing.assert_array_equal(
            masters[mpc_start:mpc_stop],
            data.master_global_dofs[data_start:data_stop],
        )
        np.testing.assert_allclose(
            coefficients[mpc_start:mpc_stop],
            data.coefficients[data_start:data_stop],
            rtol=0,
            atol=0,
        )
def test_two_twists_materialize_actual_p6_mpc_coefficients_and_reach_carrier(monkeypatch):
    from benchmarks.run_fresh_c1_p6_component import pilot_config

    cfg, axis_record = pilot_config(INPUT)
    axes = {
        "x": cfg.mesh_axis_x_values,
        "y": cfg.mesh_axis_y_values,
        "z": cfg.mesh_axis_z_values,
    }
    source_sha = axis_record["input_sha256"]
    cfg = replace(
        cfg,
        nedelec_degree=6,
        nedelec_trace_degree=None,
        nedelec_interior_degree=None,
        visualization_degree=6,
    )
    local_y = tuple(axes["y"][:3])
    local_period = float(local_y[-1] - local_y[0])
    local_cfg = replace(
        cfg,
        case_name=f"{cfg.case_name}_v10_phase_test",
        period_y=local_period,
        grating_width_y=local_period,
        mesh_axis_cell_counts=(4, 2, 5),
        mesh_axis_y_values=local_y,
        mesh_plan_id=f"{SCHEMA}.phase_test",
        mesh_plan_sha256=None,
        air_void_box_nm=None,
        cell_notch=None,
        geometry_identity=f"{SCHEMA}.phase_test",
    )
    contexts = tuple(
        np.exp(
            1j
            * (
                complex(cfg.ky).real * float(cfg.period_y)
                + 2 * np.pi * twist
            )
            / 4
        )
        for twist in (0, 1)
    )
    phases = tuple((complex(cfg.floquet_phase_x), eta**2) for eta in contexts)

    captured_carrier_calls = []
    class _Carrier:
        mode_manifest_sha256 = "a" * 64
        assembly_context_sha256 = "b" * 64

    carrier = _Carrier()

    class _Dtn:
        def __init__(self, carrier_value):
            self.carrier = carrier_value

        def destroy(self):
            return None

    class _Physical:
        def __init__(self, _volume, _dtn):
            pass

        def destroy(self):
            return None

    class _Assembler:
        compiled_gauss_identity = {"fixture": "phase-only-no-form-compile"}

    assemblers = {("top", "x"): _Assembler()}

    def fake_carrier_builder(_modes, _assemblers, mpc, _cfg, *, phase_gauge, assembly_context):
        captured_carrier_calls.append((mpc, phase_gauge, assembly_context))
        return carrier

    monkeypatch.setattr(fullspace_same_mesh_hcurl_pmg_physical, "_surface_assemblers",
                        lambda *_args, **_kwargs: assemblers)
    monkeypatch.setattr(fullspace_same_mesh_hcurl_pmg_physical, "_build_split_volume_action",
                        lambda *_args, **_kwargs: object())
    monkeypatch.setattr(fullspace_dtn_action, "build_fullspace_dtn_carrier_from_surface",
                        fake_carrier_builder)
    monkeypatch.setattr(fullspace_dtn_action, "build_fullspace_dtn_action",
                        lambda carrier_value, *, comm: _Dtn(carrier_value))
    monkeypatch.setattr(fullspace_physical_action, "FullspacePhysicalAction", _Physical)
    monkeypatch.setattr(dtn_port_3d, "_dtn_surface_quadrature_degree", lambda *_args: 1)
    monkeypatch.setattr(dtn_boundary_phase_gauge, "incident_projection_in_solver_coordinates",
                        lambda *_args: np.asarray([1.0 + 0.0j]))

    mode = SimpleNamespace(gamma=complex(cfg.ky), mode_key=("top", 0, 0, "s"))
    mode_rows = (np.asarray([0], dtype=np.int64),)
    mode_inventory = ((mode,), mode_rows, source_sha)

    level_owners = []
    mpc_owners = []
    try:
        data_none = None
        for twist, (eta, phase_override) in enumerate(zip(contexts, phases, strict=True)):
            local_levels = _build_same_mesh_levels(
                local_cfg,
                __import__("mpi4py").MPI.COMM_SELF,
                (6,),
                include_positive_coefficients=False,
                research_phase_override=phase_override,
            )
            level_owners.append(local_levels)
            floquet = local_levels["floquets"][6]
            mpc_owners.append(floquet.mpc)
            data = build_high_order_constraint_data(
                local_levels["spaces"][6],
                local_levels["mesh_data"],
                local_cfg,
                phase_override=phase_override,
            )
            assert floquet.phase_x == phase_override[0]
            assert floquet.phase_y == phase_override[1]
            assert floquet.phase_corner == phase_override[0] * phase_override[1]
            assert {"x", "y", "corner"} <= _phase_rows(data, phase_override)
            actual_coefficients, _actual_offsets = floquet.mpc.coefficients()
            _assert_mpc_matches_constraint_data(floquet.mpc, data)

            if twist == 0:
                data_none = build_high_order_constraint_data(
                    local_levels["spaces"][6],
                    local_levels["mesh_data"],
                    local_cfg,
                )
                assert {"x", "y", "corner"} <= _phase_rows(
                    data_none,
                    (complex(local_cfg.floquet_phase_x), complex(local_cfg.floquet_phase_y)),
                )
                default = build_double_floquet_mpc(
                    local_levels["spaces"][6],
                    local_levels["mesh_data"],
                    local_cfg,
                )
                mpc_owners.append(default.mpc)
                assert default.phase_x == local_cfg.floquet_phase_x
                assert default.phase_y == local_cfg.floquet_phase_y
                assert default.phase_corner == local_cfg.floquet_phase_x * local_cfg.floquet_phase_y
                default_coefficients, _default_offsets = default.mpc.coefficients()
                _assert_mpc_matches_constraint_data(default.mpc, data_none)

            setup = {
                "spaces": local_levels["spaces"],
                "floquets": local_levels["floquets"],
                "mesh": local_levels["mesh"],
                "mesh_data": local_levels["mesh_data"],
            }
            action_bundle = build_same_mesh_physical_action(
                setup,
                local_cfg,
                6,
                mode_inventory=mode_inventory,
                dtn_phase_gauge="boundary_plane",
                verify_dtn_quadrature=True,
                research_phase_override=phase_override,
            )
            try:
                carrier_mpc, gauge, context = captured_carrier_calls[-1]
                assert carrier_mpc is floquet.mpc
                assert gauge == "boundary_plane"
                np.testing.assert_allclose(
                    context["actual_floquet_phases"]["x"],
                    (phase_override[0].real, phase_override[0].imag),
                    rtol=0,
                    atol=0,
                )
                np.testing.assert_allclose(
                    context["actual_floquet_phases"]["y"],
                    (phase_override[1].real, phase_override[1].imag),
                    rtol=0,
                    atol=0,
                )
                np.testing.assert_allclose(
                    context["actual_floquet_phases"]["corner"],
                    ((phase_override[0] * phase_override[1]).real,
                     (phase_override[0] * phase_override[1]).imag),
                    rtol=0,
                    atol=0,
                )
                context_coefficients = context["MPC"]["coefficients"]
                assert context_coefficients["sha256"] == __import__(
                    "hashlib"
                ).sha256(np.ascontiguousarray(actual_coefficients).tobytes()).hexdigest()
            finally:
                destroy_same_mesh_physical_action(action_bundle)
    finally:
        for mpc in reversed(mpc_owners):
            try:
                mpc.destroy()
            except Exception:
                pass
        for levels in reversed(level_owners):
            for floquet in levels["floquets"].values():
                try:
                    floquet.mpc.destroy()
                except Exception:
                    pass
