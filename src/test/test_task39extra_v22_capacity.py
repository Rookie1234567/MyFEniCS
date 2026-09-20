"""Small V22 capacity arithmetic and native-factor lifecycle tests."""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

from src.runners.physical_dual_cell_condensed_lowmem_v20 import (
    _v22_capacity_callbacks,
    _v22_mumps_capacity_failure,
    v22_capacity_context,
)
from src.solvers.hcurl_assembly_time_condensation import (
    assembly_time_condensation_capacity_facts,
)
from src.solvers.mumps_capacity_budget_v22 import capacity_budget_v22
from src.solvers.physical_interface_schur import _prepare_factor, v11_memory_request_mb


def test_shared_local_capacity_formula_keeps_exact_p6_values_and_flags():
    facts = assembly_time_condensation_capacity_facts(
        dimension=882,
        interior_dimension=450,
        trace_dimension=432,
        raw_class_count=12,
        oriented_class_count=26,
        identity_class_count=1,
        retain_local_schur=True,
        scalar_bytes=16,
        index_bytes=4,
        real_bytes=8,
    )
    assert facts["retained_numeric_bytes_upper"] == 325283184
    assert facts["workspace_bytes_upper"] == 603388296

    general = assembly_time_condensation_capacity_facts(
        dimension=882,
        interior_dimension=450,
        trace_dimension=432,
        raw_class_count=12,
        oriented_class_count=26,
        identity_class_count=2,
        retain_local_schur=False,
        scalar_bytes=16,
        index_bytes=4,
        real_bytes=8,
    )
    assert "+0)" in general["formula"]
    assert "+2*i*i*real" in general["formula"]


def _v22_context_fixture():
    entries = []
    for side in ("top", "bottom"):
        for _ in range(40):
            entries.append(
                SimpleNamespace(
                    mode_identity={"side": side},
                    coupling_rows=np.asarray([1, 2], dtype=np.int64),
                    coupling_values=np.asarray([1.0 + 0j, 2.0 + 0j]),
                    projection_rows=np.asarray([3, 4, 5], dtype=np.int64),
                    projection_values=np.asarray([3.0 + 0j, 4.0 + 0j, 5.0 + 0j]),
                )
            )
    fine_carrier = SimpleNamespace(global_rows=667152, entries=tuple(entries))
    p4_carrier = SimpleNamespace(global_rows=201520, entries=())
    common = {
        "fine": {
            "dtn_action": SimpleNamespace(carrier=fine_carrier),
            "volume_action": SimpleNamespace(
                component_actions={
                    "h": SimpleNamespace(
                        audit={"retained_numeric_payload_local_bytes": 100}
                    )
                }
            ),
        },
        "p4": {"dtn_action": SimpleNamespace(carrier=p4_carrier)},
    }
    cfg = SimpleNamespace(mesh_axis_cell_counts_requested=(9, 5, 22))
    p6_space_facts = {
        "full_rows": 667152,
        "trace_rows": 221652,
        "active_rows": 199260,
        "slave_rows": 22392,
        "slave_master_entry_count": 22392,
        "appended_rows": 80,
        "local_tensor_dimension": 882,
        "local_interior_dimension": 450,
        "local_trace_dimension": 432,
    }
    p4_metadata = {
        "xiB_payload_estimate_bytes": 123,
        "p4_raw_class_count": 12,
        "p4_oriented_class_count": 26,
    }
    return common, cfg, p6_space_facts, p4_metadata


def test_v22_context_charges_live_h6_and_each_boundary_cell_and_direct_copies():
    common, cfg, p6_space_facts, p4_metadata = _v22_context_fixture()
    context = v22_capacity_context(
        common,
        cfg=cfg,
        p6_space_facts=p6_space_facts,
        p4_metadata=p4_metadata,
    )
    inventory = context["future_inventory_components"]
    h6_expected = 2 * 100 + 12 * 667152 * 16
    assert inventory["h6_field_and_mode_inventory_bytes"] == h6_expected
    assert context["derived_sources"]["h6_setup_estimate"][
        "common_fine_payload_bytes_live_reference"
    ] == 100
    assert "common_fine_payload_bytes_subtracted" not in context[
        "derived_sources"
    ]["h6_setup_estimate"]

    per_side = sum(
        count * (3 * 450 + 4 * 432) * 16
        + count * 4
        + count * count * 16
        for count in (40, 40)
    )
    assert inventory["p6_port_terms_inventory_bytes"] == 2 * 80 * 80 * 16 + 45 * per_side
    assert inventory["p6_mapping_inventory_bytes"] == (
        990 * ((450 + 2 * 432) * 4 + 432 * 16 + (2 * 432 + 1) * 4)
        + 45 * 80 * 4
    )
    assert inventory["p6_global_trace_map_inventory_bytes"] == (
        (221652 + 199260) * 4 + (199260 + 22392) * (4 + 16)
    )
    assert context["derived_sources"]["p6_global_trace_map"][
        "cache_identity_scatter_vectors_bytes"
    ] == 0
    # Four carrier arrays per entry, five values each, two resident
    # original/active PETSc index/value map sets; the carrier source itself is
    # excluded. Construction-time copies are workspace, not inventory.
    assert inventory["p6_direct_term_resident_inventory_bytes"] == 2 * (
        80 * 5 * (4 + 16)
    )
    direct_source = context["derived_sources"]["p6_direct_terms"]
    assert direct_source["temporary_payload_upper_bytes"] == 4 * (
        80 * 5 * (8 + 16)
    )
    assert context["future_workspace_phases"]["p6_action_construction"][
        "p6_action_temporary_window_bytes"
    ] == 128 << 20


def test_v22_context_rejects_unbound_live_dimensions_and_class_identity():
    common, cfg, p6_space_facts, p4_metadata = _v22_context_fixture()
    p6_space_facts["local_trace_dimension"] = 431
    with pytest.raises(ValueError, match="local space dimensions"):
        v22_capacity_context(
            common,
            cfg=cfg,
            p6_space_facts=p6_space_facts,
            p4_metadata=p4_metadata,
        )

    _common, _cfg, p6_space_facts, p4_metadata = _v22_context_fixture()
    p4_metadata["p4_oriented_class_count"] = 25
    with pytest.raises(ValueError, match="class identity"):
        v22_capacity_context(
            _common,
            cfg=_cfg,
            p6_space_facts=p6_space_facts,
            p4_metadata=p4_metadata,
        )


def test_v22_budget_sums_only_simultaneous_workspace_and_keeps_pool_cap():
    one_gib = 1 << 30
    budget = capacity_budget_v22(
        launch_cap_bytes=8 * one_gib,
        inventory_cap_bytes=6 * one_gib,
        current_tree_rss_bytes=one_gib,
        current_inventory_bytes=one_gib,
        future_inventory_components={"future": 100},
        future_workspace_phases={
            "setup_plus_bal_h": {
                "bal_h": 467482880,
                "p6_setup": 603388296,
            },
            "solve": {"solve_workspace": 991582208},
        },
        numeric_untouched_pool_bytes=one_gib,
        workspace_pool_cap_bytes=one_gib,
    )
    assert budget["future_workspace_peak_bytes"] == 1070871176
    assert budget["workspace_pool_cap_bytes"] == one_gib
    assert budget["status"] == "capacity_available"

    blocked = capacity_budget_v22(
        launch_cap_bytes=8 * one_gib,
        inventory_cap_bytes=6 * one_gib,
        current_tree_rss_bytes=one_gib,
        current_inventory_bytes=one_gib,
        future_inventory_components={"future": 100},
        future_workspace_phases={"setup": {"workspace": one_gib + 1}},
        numeric_untouched_pool_bytes=one_gib,
        workspace_pool_cap_bytes=one_gib,
    )
    assert blocked["status"] == "capacity_unavailable"
    assert blocked["workspace_pool_cap_bytes"] == one_gib


def test_v22_allocation_and_used_are_separate():
    observed = {
        "numeric_raw": {"infog": {"19": 900, "22": 2}},
    }
    from src.runners.physical_p4_schur_v14 import _mumps_memory_observation

    facts = _mumps_memory_observation(observed)
    assert facts["infog19_allocated_bytes_upper"] > facts["infog22_used_bytes_upper"]
    assert v11_memory_request_mb({"infog": {"16": 0, "17": 0}})["request_mb"] == 34


class _NativeQuotaFactor:
    def __init__(
        self,
        matrix,
        *,
        raise_from_numeric: bool,
        events: list[str],
        numeric_code: int = -9,
        allocated_mb: int = 900,
        used_mb: int = 2,
        destroy_assertion=None,
    ):
        self.matrix = matrix
        self.raise_from_numeric = raise_from_numeric
        self.events = events
        self.numeric_code = int(numeric_code)
        self.allocated_mb = int(allocated_mb)
        self.used_mb = int(used_mb)
        self.destroy_assertion = destroy_assertion
        self.numeric_calls = 0
        self.destroyed = False
        self.memory_limit = None
        self.settings_history = []

    def symbolic(self, matrix):
        assert matrix is self.matrix

    def info(self, _indices=()):
        self.events.append("info")
        code = self.numeric_code if self.numeric_calls else 0
        return {
            "infog": {
                "1": code,
                "9": 109,
                "16": 0,
                "17": 0,
                "19": self.allocated_mb,
                "22": self.used_mb,
                "29": 229,
                "35": 35,
                "36": 36,
                "37": 37,
            }
        }

    def symbolic_memory_settings(self):
        settings = {
            "icntl": {"7": 7, "10": 0, "14": 120, "18": 0, "22": 0, "23": 0},
            "cntl": {"1": 0.0, "3": 0.0},
        }
        settings["icntl"]["23"] = 0 if self.memory_limit is None else self.memory_limit
        self.settings_history.append(settings)
        return settings

    def set_memory_limit_mb(self, value):
        self.events.append("set_memory")
        self.memory_limit = int(value)

    def get_icntl(self, index):
        assert index == 23
        return int(self.memory_limit)

    def numeric(self, matrix):
        assert matrix is self.matrix
        self.events.append("numeric")
        self.numeric_calls += 1
        if self.raise_from_numeric:
            raise RuntimeError("synthetic native numeric failure")

    def destroy(self):
        if self.destroy_assertion is not None:
            self.destroy_assertion()
        self.events.append("destroy")
        self.destroyed = True


@pytest.mark.parametrize("raise_from_numeric", [False, True])
def test_v22_native_record_is_observed_before_destroy_and_never_retried(
    raise_from_numeric,
):
    matrix = PETSc.Mat().createAIJ((1, 1), nnz=1, comm=PETSc.COMM_SELF)
    matrix.setValue(0, 0, 1.0 + 0.0j)
    matrix.assemble()
    events: list[str] = []
    holder = {}
    native_state = {"saved": False}

    def factory(value):
        holder["factor"] = _NativeQuotaFactor(
            value, raise_from_numeric=raise_from_numeric, events=events
        )
        return holder["factor"]

    def observer(observation):
        assert holder["factor"].destroyed is False
        assert observation["numeric_raw"]["infog"]["9"] == 109
        assert observation["numeric_raw"]["infog"]["29"] == 229
        native_state.update(saved=True, numeric_raw=observation["numeric_raw"])
        events.append("observed")

    try:
        with pytest.raises(RuntimeError):
            _prepare_factor(
                matrix,
                factory,
                label="v22-fake",
                numeric_observer=observer,
            )
        factor = holder["factor"]
        assert factor.numeric_calls == 1
        assert events.index("observed") < events.index("destroy")
        assert _v22_mumps_capacity_failure(native_state)[
            "native_error_code_infog1"
        ] == -9
        assert _v22_mumps_capacity_failure({"saved": False}) is None
        before = dict(factor.settings_history[0]["icntl"])
        after = dict(factor.settings_history[1]["icntl"])
        assert factor.memory_limit == 34
        assert {key: value for key, value in after.items() if key != "23"} == {
            key: value for key, value in before.items() if key != "23"
        }
    finally:
        matrix.destroy()


def test_v22_public_entry_binds_prebuilt_zero_to_live_carrier_eighty(
    tmp_path, monkeypatch
):
    """The real V22 entry must pass the post-carrier copy to callbacks."""

    from src.geometry import v21_frozen_plan
    from src.io.physical_intermediate_profile import (
        CAPACITY_DUAL_CELL_CONDENSED_PROFILE,
        profile_facts,
    )
    from src.runners import physical_dual_cell_condensed_lowmem_v20 as worker
    from src.runners import physical_retained_outer_adapter as retained_worker
    from src.runners import task038_full3d_iterative as iterative
    from src.runners import physical_p4_schur_v14 as v14_worker
    from src.solvers import fullspace_dtn_action as dtn_worker
    from src.solvers import fullspace_same_mesh_hcurl_pmg_global as levels_worker

    common, _cfg, _p6_facts, _p4_metadata = _v22_context_fixture()
    common["fine"]["mode_sha256"] = "m" * 64
    common["fine"]["dtn_action"].carrier.mode_manifest_bytes = b"{}"
    common["fine"]["dtn_action"].carrier.mode_manifest_sha256 = "m" * 64
    common["levels"] = {"mesh_data": SimpleNamespace()}

    class CaptureCallbacks(Exception):
        pass

    class FakeRuntime:
        time_policy = "observe_only"
        shared_budget = {}
        contract = {"resources": {}}
        source_sha = "s" * 40

        def __init__(self):
            self.directory = tmp_path

        def sample(self, _label, **_kwargs):
            return {}

        def marker(self, _name, _facts=None):
            return None

        def set_phase(self, _phase):
            return None

        def check_projected(self, _label, _bytes):
            return None

    runtime = FakeRuntime()
    captured = {}
    derive_calls = []

    def fake_derive(space, _mpc, *, appended_rows):
        derive_calls.append((space, int(appended_rows)))
        if space == "p6":
            return (
                (667152, 199260, 467892, int(appended_rows)),
                {
                    "full_rows": 667152,
                    "active_rows": 199260,
                    "appended_rows": int(appended_rows),
                    "local_tensor_dimension": 882,
                    "local_interior_dimension": 450,
                    "local_trace_dimension": 432,
                },
            )
        return (
            (201520, 100000, 100000, int(appended_rows)),
            {"full_rows": 201520, "active_rows": 100000, "appended_rows": int(appended_rows)},
        )

    def capture_callbacks(**kwargs):
        captured.update(kwargs)
        raise CaptureCallbacks()

    monkeypatch.setattr(v14_worker, "_V14Runtime", lambda *a, **k: runtime)
    monkeypatch.setattr(v14_worker, "_abi_facts", lambda: {})
    monkeypatch.setattr(v14_worker, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(v14_worker, "_build_common", lambda *a, **k: common)
    monkeypatch.setattr(v14_worker, "_destroy_common", lambda *a, **k: None)
    monkeypatch.setattr(
        v14_worker, "_v14_known_preallocation_gate", lambda *a, **k: None
    )
    monkeypatch.setattr(
        levels_worker,
        "_build_same_mesh_levels",
        lambda *a, **k: {
            "spaces": {6: "p6", 4: "p4"},
            "floquets": {6: SimpleNamespace(mpc=None), 4: SimpleNamespace(mpc=None)},
        },
    )
    monkeypatch.setattr(
        dtn_worker, "build_dynamic_mode_inventory", lambda _cfg: (tuple(range(80)),)
    )
    monkeypatch.setattr(retained_worker, "derive_condensed_space_identity", fake_derive)
    monkeypatch.setattr(
        retained_worker,
        "prepare_dual_condensed_forms",
        lambda *a, **k: (
            {"p4_condensation": object(), "p6_condensation": object()},
            {"jit_options": {}},
        ),
    )
    monkeypatch.setattr(worker, "_v22_capacity_callbacks", capture_callbacks)
    monkeypatch.setattr(
        v21_frozen_plan,
        "audit_v21_mesh_identity",
        lambda *a, **k: {
            "schema": "mock",
            "variant": "mock",
            "geometry_identity": {},
            "actual_axis_cell_counts": [9, 5, 22],
            "owned_cell_count": 990,
            "notch_candidate_count": 0,
            "notch": {"changed_cells": 0},
            "material_layout_sha256": "a" * 64,
            "geometry_entity_sha256": "b" * 64,
        },
    )
    monkeypatch.setattr(
        "src.io.input_validation.simulation_config_3d_from_normalized",
        lambda _payload: _cfg,
    )

    payload = {
        "method": {"kind": "full3d_iterative"},
        "solver": {
            "preconditioner": CAPACITY_DUAL_CELL_CONDENSED_PROFILE,
            "stage": "Z3_ORIGINAL_H7P5",
        },
        "derived": {
            "physical_intermediate_profile": profile_facts(
                CAPACITY_DUAL_CELL_CONDENSED_PROFILE
            )
        },
    }
    result = iterative.run_full3d_iterative(payload, tmp_path, source_sha="s" * 40)

    assert result["passed"] is False
    assert derive_calls[0][1] == 0
    assert captured["final_space_facts"]["appended_rows"] == 80
    assert captured["final_space_facts"]["appended_rows"] == len(
        common["fine"]["dtn_action"].carrier.entries
    )


class _CallbackRuntime:
    def __init__(self, directory):
        self.directory = directory
        self.inventory_cap = 6 * (1 << 30)
        self.inventory_used_bytes = 1 << 30
        self.workspace_cap = 1 << 30
        self.workspace_live_bytes = 0
        self.events = []
        self.samples = []

    def sample(self, label, *, enforce=False):
        self.samples.append((label, bool(enforce)))
        return {"launch_cap_bytes": 8 * (1 << 30), "rss_bytes": 1}

    def marker(self, name, facts=None):
        if name == "v22_numeric_observed_before_post_gate":
            assert (self.directory / "v22_numeric_native_facts.json").exists()
        self.events.append((name, facts))

    def check_inventory_projected(self, _label, _bytes):
        return None


def test_v22_production_callbacks_bind_final_80_and_gate_allocated_before_destroy(
    tmp_path,
):
    """Run the shared worker callbacks around the real factor lifecycle hook."""

    from src.runners.physical_p4_schur_v14 import V14ResourceStop, _write_json

    common, cfg, p6_facts, p4_metadata = _v22_context_fixture()
    pre_facts = dict(p6_facts)
    pre_facts["appended_rows"] = 0
    final_facts = dict(p6_facts)
    assert pre_facts["appended_rows"] == 0
    assert final_facts["appended_rows"] == 80
    with pytest.raises(ValueError, match="FE/MPC facts"):
        v22_capacity_context(
            common,
            cfg=cfg,
            p6_space_facts=pre_facts,
            p4_metadata=p4_metadata,
        )

    runtime = _CallbackRuntime(tmp_path)
    summary = {"status": "STARTED"}
    native_state = {"saved": False}
    callbacks = _v22_capacity_callbacks(
        runtime=runtime,
        common=common,
        cfg=cfg,
        final_space_facts=final_facts,
        p4_metadata=p4_metadata,
        directory=tmp_path,
        source_sha="s" * 40,
        summary=summary,
        native_observation_state=native_state,
        write_json=_write_json,
    )
    memory_request_builder, observer, continuation_gate = callbacks

    matrix = PETSc.Mat().createAIJ((1, 1), nnz=1, comm=PETSc.COMM_SELF)
    matrix.setValue(0, 0, 1.0 + 0.0j)
    matrix.assemble()
    events: list[str] = []
    holder = {}

    def factory(value):
        def assert_native_saved():
            assert (tmp_path / "v22_numeric_native_facts.json").exists()

        holder["factor"] = _NativeQuotaFactor(
            value,
            raise_from_numeric=False,
            events=events,
            numeric_code=0,
            allocated_mb=100000,
            used_mb=2,
            destroy_assertion=assert_native_saved,
        )
        return holder["factor"]

    try:
        with pytest.raises(V14ResourceStop, match="allocated factor"):
            _prepare_factor(
                matrix,
                factory,
                label="v22-production-callbacks",
                resource_sample=lambda: runtime.sample("factor_resource"),
                memory_request_builder=memory_request_builder,
                numeric_observer=observer,
                post_numeric_gate=continuation_gate,
            )
        factor = holder["factor"]
        assert factor.numeric_calls == 1
        assert factor.memory_limit is not None and factor.memory_limit > 0
        assert summary["capacity_trial"]["identity"]["p6_port_count"] == 80
        assert native_state["saved"] is True
        native = json.loads(
            (tmp_path / "v22_numeric_native_facts.json").read_text()
        )
        assert native["native_infog"]["19"] == 100000
        assert native["native_infog"]["22"] == 2
        assert any(
            name == "v22_continuation_allocated_gate_failed"
            for name, _facts in runtime.events
        )
        assert any(
            name == "v22_numeric_observed_before_post_gate"
            for name, _facts in runtime.events
        )
        # The fake factor's destroy hook has already asserted that the
        # production observer durably saved the native record first.
        assert factor.destroyed is True
        assert factor.settings_history[0]["icntl"]["23"] == 0
        assert factor.settings_history[1]["icntl"]["23"] == factor.memory_limit
        assert not any(
            label == "v22_continuation_resource_gate" for label, _ in runtime.samples
        )
    finally:
        matrix.destroy()


class _V23PhysicalPressureRuntime:
    """Small runtime double exercising the production callback sequence."""

    memory_policy = "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23"
    inventory_cap = None
    workspace_cap = None
    inventory_used_bytes = 1 << 30
    workspace_live_bytes = 0

    def __init__(self, directory, *, stop_on_pressure=False):
        self.directory = directory
        self.stop_on_pressure = bool(stop_on_pressure)
        self.events = []
        self.samples = []

    def sample(self, label, *, enforce=False):
        self.samples.append((label, bool(enforce)))
        if self.stop_on_pressure and enforce and "continuation_physical_pressure" in label:
            from src.runners.physical_p4_schur_v14 import V14ResourceStop

            raise V14ResourceStop("synthetic MemAvailable physical-pressure stop")
        return {
            "launch_cap_bytes": 12 * (1 << 30),
            "rss_bytes": 1 << 30,
            "memory_envelope": {
                "effective_available_bytes": 12 * (1 << 30),
                "reserve_bytes": 128 << 20,
            },
        }

    def marker(self, name, facts=None):
        if name == "v23_numeric_observed_before_post_gate":
            assert (self.directory / "v23_numeric_native_facts.json").exists()
        self.events.append((name, facts))

    def check_inventory_projected(self, _label, _bytes):
        pytest.fail("V23 must not use the static inventory continuation gate")


@pytest.mark.parametrize("stop_on_pressure", [False, True])
def test_v23_production_callbacks_use_live_pressure_after_numeric(
    tmp_path, stop_on_pressure
):
    """Exercise builder -> native observer -> continuation gate as one chain."""

    from src.runners.physical_p4_schur_v14 import V14ResourceStop, _write_json

    common, cfg, p6_facts, p4_metadata = _v22_context_fixture()
    runtime = _V23PhysicalPressureRuntime(
        tmp_path, stop_on_pressure=stop_on_pressure
    )
    summary = {"status": "STARTED"}
    native_state = {"saved": False}
    memory_request_builder, observer, continuation_gate = _v22_capacity_callbacks(
        runtime=runtime,
        common=common,
        cfg=cfg,
        final_space_facts=p6_facts,
        p4_metadata=p4_metadata,
        directory=tmp_path,
        source_sha="s" * 40,
        summary=summary,
        native_observation_state=native_state,
        write_json=_write_json,
        memory_policy="PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23",
        native_quota_mb=4687,
        evidence_prefix="v23",
    )

    matrix = PETSc.Mat().createAIJ((1, 1), nnz=1, comm=PETSc.COMM_SELF)
    matrix.setValue(0, 0, 1.0 + 0.0j)
    matrix.assemble()
    holder = {}

    def factory(value):
        def assert_native_saved():
            assert (tmp_path / "v23_numeric_native_facts.json").exists()

        holder["factor"] = _NativeQuotaFactor(
            value,
            raise_from_numeric=False,
            events=[],
            numeric_code=0,
            allocated_mb=5000,
            used_mb=100,
            destroy_assertion=assert_native_saved,
        )
        return holder["factor"]

    try:
        if stop_on_pressure:
            with pytest.raises(V14ResourceStop, match="physical-pressure"):
                _prepare_factor(
                    matrix,
                    factory,
                    label="v23-production-callbacks",
                    resource_sample=lambda: runtime.sample("factor_resource"),
                    memory_request_builder=memory_request_builder,
                    numeric_observer=observer,
                    post_numeric_gate=continuation_gate,
                )
        else:
            factor, _factor_facts = _prepare_factor(
                matrix,
                factory,
                label="v23-production-callbacks",
                resource_sample=lambda: runtime.sample("factor_resource"),
                memory_request_builder=memory_request_builder,
                numeric_observer=observer,
                post_numeric_gate=continuation_gate,
            )
            factor.destroy()
        factor = holder["factor"]
        assert factor.numeric_calls == 1
        assert factor.memory_limit == 4687
        assert native_state["saved"] is True
        assert (tmp_path / "v23_numeric_native_facts.json").exists()
        assert any(
            name == "v23_continuation_native_observed" for name, _ in runtime.events
        )
        assert not any(
            "allocated_gate_failed" in name for name, _ in runtime.events
        )
        if stop_on_pressure:
            assert any(
                name == "v23_continuation_physical_pressure_gate_failed"
                for name, _ in runtime.events
            )
        else:
            assert any(
                name == "v23_continuation_physical_pressure_gate"
                for name, _ in runtime.events
            )
    finally:
        matrix.destroy()


def test_v23_watchdog_policy_drops_legacy_static_caps_without_changing_defaults(monkeypatch):
    from benchmarks import subreaper_watchdog

    monkeypatch.setattr(
        subreaper_watchdog,
        "wsl_memory_snapshot",
        lambda: {
            "mem_total_bytes": 32 << 30,
            "mem_available_bytes": 20 << 30,
        },
    )
    monkeypatch.setattr(subreaper_watchdog, "current_cgroup_path", lambda: None)
    legacy = subreaper_watchdog.memory_envelope()
    physical = subreaper_watchdog.memory_envelope(
        "PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23"
    )
    assert legacy["reserve_bytes"] == max(4 << 30, int(0.15 * (32 << 30)))
    assert legacy["launch_cap_bytes"] <= 12_000_000_000
    assert physical["reserve_bytes"] == 128 << 20
    assert physical["launch_cap_bytes"] == (20 << 30) - (128 << 20)
    assert physical["static_tree_cap_bytes"] is None
    assert subreaper_watchdog.runtime_tree_cap(
        8 << 30,
        1 << 30,
        physical,
        memory_policy="PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23",
    ) == physical["launch_cap_bytes"] + (1 << 30)
    assert subreaper_watchdog.runtime_tree_cap(8 << 30, 1 << 30, legacy) == 8 << 30
