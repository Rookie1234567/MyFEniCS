from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

from src.solvers.task40_v10_p6_yorbit import (
    Q_ASSEMBLY_LEGACY,
    _task40_v30_load_sector_q_csr_pair,
    _task40_v30_ordered_mode_key_sha256,
    assemble_task40_v10_selected_sector_blocks,
)


def test_selected_twist_assembly_builds_only_the_requested_global_q():
    class Coordinates:
        def q_map(self, branch, *, allocation_gate):
            allocation_gate("map", {"additional_payload_bytes": 0, "workspace_bytes": 0})
            column = np.zeros(4, dtype=np.complex128)
            column[branch] = 1.0
            return sparse.csr_matrix(column.reshape(4, 1))

    class Action:
        def __init__(self):
            self.iterations = 0

        def iter_reduced_contributions(self, *, allocation_gate):
            self.iterations += 1
            yield (
                np.arange(4, dtype=np.int32),
                np.arange(4, dtype=np.int32),
                np.diag(np.asarray([2.0, 7.0, 11.0, 13.0], dtype=np.complex128)),
                "fixture/diagonal",
            )

    action = Action()
    matrices, audit = assemble_task40_v10_selected_sector_blocks(
        action,
        Coordinates(),
        SimpleNamespace(global_q_indices=(0, 4), twist_index=0),
        selected_global_q_indices=(4,),
        allocation_gate=lambda *_args: None,
        assembly_strategy=Q_ASSEMBLY_LEGACY,
    )

    assert set(matrices) == {4}
    assert matrices[4].shape == (1, 1)
    assert matrices[4].toarray()[0, 0] == 7.0 + 0.0j
    assert audit["unselected_q_csr_rebuilt"] is False
    assert audit["fourier_diagonalization_gate"] == "DEFERRED_TO_NATIVE_QUALIFICATION"
    assert action.iterations == 1


def test_v32_worker_handoff_requires_both_saved_map_audits():
    from src.runners.task40_v10_worker import _task40_v32_owner_bound_q_maps

    q_maps = {0: object(), 4: object()}
    owner = {
        "q_maps_by_q": q_maps,
        "owner_receipt": {
            "saved_q0_q4_map_binding": {
                "q0": {"passed": True},
                "q4": {"passed": True},
            }
        },
    }

    assert _task40_v32_owner_bound_q_maps({"review_version": "V31"}, owner) is None
    assert _task40_v32_owner_bound_q_maps({"review_version": "V32"}, owner) is q_maps

    owner["owner_receipt"]["saved_q0_q4_map_binding"]["q4"]["passed"] = False
    with pytest.raises(ValueError, match="passing saved q0/q4 binding audit"):
        _task40_v32_owner_bound_q_maps({"review_version": "V32"}, owner)


def test_v30_sector_adapter_binds_actual_twist_maps_h_modes_and_q0_lookup():
    mode = SimpleNamespace(side="bottom", m=0, n=0, polarization="s")

    class Profile:
        name = "fixture-profile"

        def identity(self):
            return {"name": self.name, "q_count": 8}

    class Coordinates:
        def q_map(self, branch, *, allocation_gate):
            value = np.zeros(4, dtype=np.complex128)
            value[branch] = 1.0
            return sparse.csr_matrix(value.reshape(4, 1))

    class Provider:
        profile = "fixture-profile"
        entries = {q: {} for q in range(8)}

        def __init__(self):
            self.calls = []

        def load(self, q_index, twist_index, **kwargs):
            self.calls.append((q_index, twist_index, kwargs))
            return sparse.csr_matrix(np.asarray([[q_index + 1j]], dtype=np.complex128)), {
                "q_index": q_index,
                "twist_index": twist_index,
                "csr_manifest_sha256": f"{q_index + 1:064x}",
                "native_qualification_sha256": f"{q_index + 9:064x}",
                "qualification_kind": (
                    "LEGACY_QUALIFICATION_IMPORTED_OPERATOR_BINDINGS_DERIVED"
                    if q_index == 0
                    else "V30_NATIVE_PASS"
                ),
                "qualification_status": "PASS",
            }

    condensed = SimpleNamespace(
        full_rows=4,
        trace_constraints=SimpleNamespace(original_to_active={0: 0, 2: 1}),
    )
    action = SimpleNamespace(condensed=condensed)
    bundle = {"mode_sha256": "3" * 64, "modes": (mode,)}
    expected_legacy = {
        "input_sha256": "1" * 64,
        "physical_model_sha256": "6" * 64,
        "mode_manifest_sha256": "3" * 64,
    }
    runtime_identity = {
        "scientific_input_sha256": "1" * 64,
        "ordered_mode_key_sha256": _task40_v30_ordered_mode_key_sha256((mode,)),
        "execution_identity": {"source_sha": "2" * 40, "window_sha256": "5" * 64},
        "legacy_q0_identity": expected_legacy,
    }
    provider = Provider()
    matrices, audit = _task40_v30_load_sector_q_csr_pair(
        provider,
        action=action,
        coordinates=Coordinates(),
        context=SimpleNamespace(twist_index=0, global_q_indices=(0, 4)),
        local_h=np.asarray([1.0, 2.0], dtype=np.float64),
        profile=Profile(),
        mode_descriptor=bundle,
        mode_inventory=((mode,), ({"mode_index": 0},), "3" * 64),
        runtime_identity=runtime_identity,
        allocation_gate=lambda *_args: None,
    )

    assert set(matrices) == {0, 4}
    assert [(q, twist) for q, twist, _ in provider.calls] == [(0, 0), (4, 0)]
    assert provider.calls[0][2]["expected_operator_identity"]["ordered_mode_sha256"] == (
        runtime_identity["ordered_mode_key_sha256"]
    )
    assert provider.calls[0][2]["expected_q0_active_lookup"].tolist() == [0, -1, 1, -1]
    assert provider.calls[1][2]["expected_q0_active_lookup"] is None
    assert audit["native_operator_requalification_performed"] is False
    assert [row["q_index"] for row in audit["qualification_receipts"]] == [0, 4]
    assert [row["qualification_kind"] for row in audit["qualification_receipts"]] == [
        "LEGACY_QUALIFICATION_IMPORTED_OPERATOR_BINDINGS_DERIVED",
        "V30_NATIVE_PASS",
    ]


def test_v32_twist0_handoff_accepts_provider_q4_and_requires_real_q0_q4_receipts():
    from src.runners.task40_v10_worker import _task40_v31_merge_twist0_q_csr_audit

    matrices = {
        0: sparse.eye(2, dtype=np.complex128, format="csr"),
        4: sparse.eye(3, dtype=np.complex128, format="csr"),
    }
    q0_receipt = {
        "q_index": 0,
        "qualification_kind": "LEGACY_QUALIFICATION_IMPORTED_OPERATOR_BINDINGS_DERIVED",
        "qualification_status": "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK",
        "legacy_q0_import": {"status": "PASS"},
    }
    q4_receipt = {
        "q_index": 4,
        "qualification_kind": "V30_NATIVE_PASS",
        "qualification_status": "PASS",
    }
    q0_entry = {"q_index": 0, "qualification_status": "PASS"}
    q4_entry = {"q_index": 4, "qualification_status": "PASS"}
    donor_binding = {"status": "PASS_LIVE_MAP_H_LOOKUP_BOUND"}

    # V32 reopens both immutable matrices through the provider; the old q0
    # native status is intentionally kept in its accepted legacy form.
    all_matrices, audit = _task40_v31_merge_twist0_q_csr_audit(
        matrices,
        {
            "qualification_receipts": [q0_receipt, q4_receipt],
            "selector_entries": [q0_entry, q4_entry],
        },
        {},
        {},
        donor_binding=donor_binding,
    )
    assert set(all_matrices) == {0, 4}
    assert audit["all_complete_native_pass"] is True
    assert audit["qualification_receipts"] == [q0_receipt, q4_receipt]

    # A fresh q4 preparer contributes its real receipt beside provider q0.
    all_matrices, audit = _task40_v31_merge_twist0_q_csr_audit(
        {0: matrices[0]},
        {"qualification_receipts": [q0_receipt], "selector_entries": [q0_entry]},
        {4: matrices[4]},
        {"qualification_receipts": [q4_receipt], "selector_entries": [q4_entry]},
        donor_binding=donor_binding,
    )
    assert set(all_matrices) == {0, 4}
    assert audit["all_complete_native_pass"] is True
    assert [
        entry for entry in audit["selector_entries"]
        if int(entry.get("q_index", -1)) == 4
    ] == [q4_entry]

    with pytest.raises(ValueError, match="lacks COMPLETE CSR and native PASS"):
        _task40_v31_merge_twist0_q_csr_audit(
            matrices,
            {
                "qualification_receipts": [q0_receipt],
                "selector_entries": [q0_entry, q4_entry],
            },
            {},
            {},
            donor_binding=donor_binding,
        )


def test_v33_sector_first_builder_keeps_real_selector_and_native_q_preparer(
    tmp_path, monkeypatch
):
    """Exercise real q scheduling/import/native preparation with only FE/factor mocked."""
    import hashlib

    from types import SimpleNamespace

    from mpi4py import MPI

    from src.common.config_3d import SimulationConfig3D
    from src.solvers import (
        dtn_boundary_phase_gauge,
        fullspace_same_mesh_hcurl_pmg_global,
        fullspace_same_mesh_hcurl_pmg_physical,
        task40_v10_p6_mumps,
        task40_v10_p6_periodic_profile,
        task40_v10_p6_yorbit,
        task40_v30_qualified_q_csr,
        task40_v30_selected_q_csr,
    )

    profile = task40_v10_p6_periodic_profile.Task40V10P6PeriodicProfile(
        name="task40extra_test_v33_sector_first",
        global_cell_axes=(1, 8, 1),
        global_cell_count=8,
        global_storage_rows=16,
        global_independent_rows=16,
        global_interior_rows=8,
        global_trace_rows=8,
        q_count=8,
        rows_per_q=2,
        trace_rows_per_q=1,
        local_y_cells=2,
        replication_count=4,
        local_cell_count=2,
        local_storage_rows=4,
        local_independent_rows=4,
        local_interior_rows=0,
        local_trace_rows=2,
        local_width_per_q=2,
        q_port_counts=(1,) * 8,
        sector_port_counts=(2,) * 4,
    )
    cfg = SimulationConfig3D(
        nedelec_degree=6,
        mesh_axis_cell_counts=profile.global_cell_axes,
        geometry_identity="task40_v33_sector_first_fixture",
    )
    axes = {
        "x": tuple(np.linspace(0.0, cfg.period_x, 2)),
        "y": tuple(np.linspace(0.0, cfg.period_y, 9)),
        "z": tuple(np.linspace(cfg.z_min, cfg.z_max, 2)),
    }
    dy = axes["y"][1] - axes["y"][0]
    modes = tuple(
        SimpleNamespace(
            side="top",
            m=q,
            n=0,
            polarization="s",
            gamma=(complex(cfg.ky).real * cfg.period_y + 2.0 * np.pi * q)
            / (8.0 * dy),
            mode_key=f"fixture-q{q}",
        )
        for q in range(8)
    )
    mode_rows = tuple(
        {"side": "top", "m": q, "n": 0, "polarization": "s"}
        for q in range(8)
    )
    mode_sha = "a" * 64
    mode_inventory = (modes, mode_rows, mode_sha)
    global_h = np.asarray([1.0 + 0.1 * mode.m for mode in modes], dtype=np.float64)
    monkeypatch.setattr(
        dtn_boundary_phase_gauge,
        "assembly_projection_denominator",
        lambda mode, _cfg, _plane: 1.0 + 0.1 * mode.m,
    )
    contexts = task40_v10_p6_yorbit.build_task40_v10_sector_contexts(
        modes,
        cfg,
        axes,
        expected_q_counts=profile.q_port_counts,
        expected_sector_counts=profile.sector_port_counts,
    )
    global_h_sha = hashlib.sha256(
        np.ascontiguousarray(global_h).view(np.uint8)
    ).hexdigest()
    scientific_sha = "1" * 64
    execution_identity = {"source_sha": "c" * 40, "window_sha256": "d" * 64}
    matrix_source_identity = {"source_sha": "e" * 40, "window_sha256": "f" * 64}
    reduced_matrix = np.diag(np.asarray([2.0, 3.0, 5.0, 7.0], dtype=np.complex128))

    def q_map(branch):
        row = int(branch)
        port_row = 2 + row
        result = sparse.csr_matrix(
            (
                np.asarray([1.0 + 0j, 1.0 + 0j], dtype=np.complex128),
                (np.asarray([row, port_row]), np.asarray([0, 1])),
            ),
            shape=(4, 2),
            dtype=np.complex128,
        )
        result.indices = result.indices.astype(np.int32, copy=False)
        result.indptr = result.indptr.astype(np.int32, copy=False)
        return result

    class Coordinates:
        width = 2

        def __init__(self, context):
            self.context = context

        def q_map(self, branch, *, allocation_gate):
            allocation_gate("fixture/q-map", {"additional_payload_bytes": 0, "workspace_bytes": 0})
            return q_map(branch)

    def local_h_for(context):
        return np.asarray(global_h[context.original_mode_indices], dtype=np.float64)

    q0_maps = {0: q_map(0), 4: q_map(1)}
    twist0 = contexts[0]
    twist0_h = local_h_for(twist0).astype(np.complex128)
    ordered_mode_sha = task40_v10_p6_yorbit._task40_v30_ordered_mode_key_sha256(modes)

    def write_json(path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
        path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    provider_entries = []
    for q_index, branch in ((0, 0), (4, 1)):
        operator_identity = task40_v30_selected_q_csr.selected_q_operator_identity(
            scientific_input_sha256=scientific_sha,
            profile_identity=profile.identity(),
            ordered_modes=modes,
            q_map=q0_maps[q_index],
            original_h=twist0_h,
        )
        matrix = sparse.csr_matrix(
            q0_maps[q_index].conjugate().T @ reduced_matrix @ q0_maps[q_index],
            dtype=np.complex128,
        )
        matrix.sum_duplicates()
        matrix.sort_indices()
        matrix.indices = matrix.indices.astype(np.int32, copy=False)
        matrix.indptr = matrix.indptr.astype(np.int32, copy=False)
        entry_root = tmp_path / f"saved_q{q_index}"
        arrays = {}
        for name, array in (
            ("data", matrix.data),
            ("indices", matrix.indices),
            ("indptr", matrix.indptr),
        ):
            path = entry_root / f"q{q_index}_{name}.npy"
            path.parent.mkdir(parents=True, exist_ok=True)
            np.save(path, array, allow_pickle=False)
            arrays[name] = {
                "path": path.name,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        manifest_path = entry_root / f"q{q_index}_manifest.json"
        manifest_sha = write_json(
            manifest_path,
            {
                "schema": task40_v30_qualified_q_csr.V30_Q_CSR_MANIFEST_SCHEMA,
                "status": "COMPLETE_CSR",
                "profile": profile.name,
                "q_index": q_index,
                "twist_index": 0,
                "shape": list(matrix.shape),
                "stored_structural_slots": int(matrix.nnz),
                "csr_index_dtype": np.dtype(np.int32).str,
                "csr_data_dtype": np.dtype(np.complex128).str,
                "operator_identity": operator_identity,
                "matrix_source_identity": matrix_source_identity,
                "csr_artifacts": arrays,
            },
        )
        native_path = entry_root / f"q{q_index}_native.json"
        native_sha = write_json(
            native_path,
            {
                "schema": task40_v30_qualified_q_csr.V30_Q_CSR_NATIVE_SCHEMA,
                "status": "PASS",
                "q_index": q_index,
                "twist_index": 0,
                "csr_manifest_sha256": manifest_sha,
                "operator_identity": operator_identity,
                "matrix_source_identity": matrix_source_identity,
                "execution_identity": execution_identity,
                "four_complete_csr_actions_passed": True,
                "paired_sector_leakage_passed": True,
                "maximum_relative_error": 0.0,
            },
        )
        provider_entries.append(
            {
                "q_index": q_index,
                "twist_index": 0,
                "shape": list(matrix.shape),
                "operator_identity": operator_identity,
                "matrix_source_identity": matrix_source_identity,
                "execution_identity": execution_identity,
                "csr_manifest": {"path": str(manifest_path), "sha256": manifest_sha},
                "native_qualification": {"path": str(native_path), "sha256": native_sha},
            }
        )
    selector_path = tmp_path / "qualified_selector.json"
    selector_sha = write_json(
        selector_path,
        {
            "schema": task40_v30_qualified_q_csr.V30_Q_CSR_SELECTOR_SCHEMA,
            "profile": profile.name,
            "q_csr_entries": provider_entries,
        },
    )
    provider = task40_v30_qualified_q_csr.QualifiedQCSRProvider(
        selector_path,
        selector_sha256=selector_sha,
        repo_root=tmp_path,
        path_resolver=lambda path: Path(path).resolve(),
        allocation_gate=lambda *_args: None,
    )
    provider_loads = []
    original_provider_load = provider.load

    def record_provider_load(q_index, twist_index, **kwargs):
        provider_loads.append((q_index, twist_index))
        return original_provider_load(q_index, twist_index, **kwargs)

    monkeypatch.setattr(provider, "load", record_provider_load)

    pattern_qs = []
    fill_qs = []
    native_qs = []
    original_pattern = task40_v30_selected_q_csr.build_saved_selected_q_pattern
    original_fill = task40_v30_selected_q_csr.fill_saved_selected_q_values
    original_native = task40_v30_selected_q_csr.run_selected_q_native_actions

    def record_pattern(source, q_map_value, **kwargs):
        pattern_qs.append(int(kwargs["q_index"]))
        assert int(kwargs["q_index"]) not in {0, 4}
        return original_pattern(source, q_map_value, **kwargs)

    def record_fill(source, matrix, q_map_value, **kwargs):
        fill_qs.append(int(kwargs["q_index"]))
        assert int(kwargs["q_index"]) not in {0, 4}
        return original_fill(source, matrix, q_map_value, **kwargs)

    def record_native(**kwargs):
        native_qs.append(int(kwargs["selected_q_index"]))
        assert int(kwargs["selected_q_index"]) not in {0, 4}
        return original_native(**kwargs)

    monkeypatch.setattr(task40_v30_selected_q_csr, "build_saved_selected_q_pattern", record_pattern)
    monkeypatch.setattr(task40_v30_selected_q_csr, "fill_saved_selected_q_values", record_fill)
    monkeypatch.setattr(task40_v30_selected_q_csr, "run_selected_q_native_actions", record_native)

    class Mpc:
        slaves = np.asarray([], dtype=np.int32)

        def __init__(self):
            self.destroyed = False

        def destroy(self):
            self.destroyed = True

    class Mesh:
        def __init__(self, cells):
            self.topology = SimpleNamespace(
                index_map=lambda _dimension: SimpleNamespace(size_local=cells)
            )

    class Entities:
        def __init__(self, full_rows, independent_rows, width):
            self.full_rows = full_rows
            self.independent = tuple(range(independent_rows))
            self.width = width

        def named_backing_arrays(self, _prefix):
            return {}

    class FullLayout:
        def __init__(self, _entities, _cfg, *, expected_inventory):
            assert expected_inventory["ny"] == 8
            self.full_rows = 16
            self.width = 2
            self.audit = {"dimension_counts": [0, 0, 0, 8]}

    class ReducedAction:
        reduced_size = 4
        buffer_inventory = {}

        def __init__(self):
            self.condensed = SimpleNamespace(
                full_rows=4,
                active_rows=2,
                active_interior_rows=0,
                appended_rows=2,
                comm=MPI.COMM_SELF,
                trace_constraints=SimpleNamespace(original_to_active={0: 0, 1: 1}),
                build_audit={},
            )
            self.destroyed = False

        def iter_reduced_contribution_layouts(self, *, hhat_block_columns=None):
            rows = np.arange(4, dtype=np.int32)
            yield rows, rows, "fixture/local"

        def iter_reduced_contributions(self, **_kwargs):
            rows = np.arange(4, dtype=np.int32)
            yield rows, rows, reduced_matrix.copy(), "fixture/diagonal-action"

        def recover_storage(self, reduced, *, expand_trace=False):
            return np.asarray(reduced, dtype=np.complex128).copy()

        def reduce_rhs(self, rhs, *, port_rhs=None, rhs_is_mpc_dual=False):
            result = np.asarray(rhs, dtype=np.complex128).copy()
            if port_rhs is not None:
                result[2:] += np.asarray(port_rhs, dtype=np.complex128)
            return result

        def apply_B_full(self, _ports):
            return np.zeros(4, dtype=np.complex128)

        def apply_D_full(self, _field):
            return np.zeros(2, dtype=np.complex128)

        def _apply_original_h(self, _ports):
            return np.zeros(2, dtype=np.complex128)

        def destroy(self):
            self.destroyed = True

    class VolumeAction:
        def apply(self, vector):
            values = vector.getArray()
            copied = values.copy()
            values[:] = reduced_matrix @ copied
            return vector

    banks = []
    owner_rows = []

    def local_owner_fixture(_cfg, _axes, **kwargs):
        context = kwargs["context"]
        transform_bank = kwargs["transform_bank"]
        if banks:
            assert transform_bank is banks[0]
        else:
            banks.append(transform_bank)
        stage_callback = kwargs.get("stage_callback")
        if stage_callback is not None:
            stage_callback({"phase": "fixture_local_owner", "status": "COMPLETE"})
        local_modes = tuple(kwargs["global_modes"][int(i)] for i in context.original_mode_indices)
        local_rows = tuple(kwargs["global_mode_rows"][int(i)] for i in context.original_mode_indices)
        coordinates = Coordinates(context)
        action = ReducedAction()
        owner = {
            "context": context,
            "levels": {
                "floquets": {6: SimpleNamespace(mpc=Mpc())},
                "mesh_data": SimpleNamespace(mesh=Mesh(2)),
            },
            "bundle": {"action": SimpleNamespace(destroy=lambda: None), "volume_action": VolumeAction()},
            "system": None,
            "action": action,
            "entities": Entities(4, 4, 2),
            "coordinates": coordinates,
            "trace": object(),
            "local_modes": local_modes,
            "mode_inventory": (local_modes, local_rows, mode_sha),
            "local_h": local_h_for(context),
            "global_h_sha256": global_h_sha,
            "transform_bank": transform_bank,
            "q_maps_by_q": {
                int(q): q_map(branch)
                for branch, q in enumerate(context.global_q_indices)
            },
            "owner_receipt": {
                "global_mode_sha256": mode_sha,
                "created_before_global_reference": True,
            },
        }
        owner_rows.append(owner)
        return owner

    monkeypatch.setattr(
        task40_v10_p6_yorbit, "build_task40_v10_p6_local_sector_owner", local_owner_fixture
    )
    import src.solvers.y_orbit_transform_bank as transform_bank_module

    original_bank_type = transform_bank_module.YOrbitTransformBank

    def record_bank(*args, **kwargs):
        bank = original_bank_type(*args, **kwargs)
        banks.append(bank)
        return bank

    monkeypatch.setattr(transform_bank_module, "YOrbitTransformBank", record_bank)

    from src.runners.task40_v10_worker import _task40_v33_late_twist0_owner_preparer

    q4_pending = {"status": "NUMERIC_COMPLETE_NATIVE_PENDING"}
    late_owner_bank_calls = []

    def prepare_twist0_owner(pending, *, transform_bank):
        assert pending is q4_pending
        assert banks and transform_bank is banks[0]
        late_owner_bank_calls.append(transform_bank)
        return local_owner_fixture(
            cfg,
            axes,
            context=twist0,
            global_modes=modes,
            global_mode_rows=mode_rows,
            global_mode_sha256=mode_sha,
            global_h=global_h,
            transform_bank=transform_bank,
        )

    late_twist0_owner_preparer = _task40_v33_late_twist0_owner_preparer(
        q4_pending,
        prepare_twist0_owner=prepare_twist0_owner,
        prebuilt_q_csr=lambda: None,
    )

    events = []
    schedule = []

    class FailBeforeFactor(Exception):
        pass

    def global_levels_fixture(*_args, **_kwargs):
        schedule.append("global_mesh")
        return {
            "mesh": Mesh(8),
            "mesh_data": SimpleNamespace(mesh=Mesh(8)),
            "spaces": {6: object()},
            "floquets": {6: SimpleNamespace(mpc=Mpc())},
        }

    def global_physical_fixture(_levels, _cfg, _degree, **kwargs):
        schedule.append("global_physical")
        assert any(name == "task40_v33_sector_products_durable" for name, _ in events)
        callback = kwargs.get("stage_callback")
        if callback is not None:
            callback({"phase": "carrier_build", "status": "COMPLETE", "mode_count": 8})
        carrier = SimpleNamespace(
            entries=[SimpleNamespace(normalization_h=value) for value in global_h],
            mode_manifest_sha256=mode_sha,
        )
        return {
            "action": SimpleNamespace(destroy=lambda: None),
            "modes": modes,
            "mode_rows": mode_rows,
            "mode_sha256": mode_sha,
            "dtn_action": SimpleNamespace(carrier=carrier),
        }

    monkeypatch.setattr(
        fullspace_same_mesh_hcurl_pmg_global, "_build_same_mesh_levels", global_levels_fixture
    )
    monkeypatch.setattr(
        fullspace_same_mesh_hcurl_pmg_physical,
        "build_same_mesh_physical_action",
        global_physical_fixture,
    )
    monkeypatch.setattr(
        task40_v10_p6_yorbit,
        "collect_y_orbit_entities",
        lambda *_args, **_kwargs: Entities(16, 16, 2),
    )
    monkeypatch.setattr(task40_v10_p6_yorbit, "Task40V10FullLayout", FullLayout)
    monkeypatch.setattr(
        task40_v10_p6_yorbit,
        "TwoCellNativeTransport",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(
        task40_v10_p6_mumps,
        "AllQExactMumps",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FailBeforeFactor()),
    )

    callback_order = []

    def actual_q_preparer(**kwargs):
        context = kwargs["context"]
        sector_qs = tuple(map(int, context.global_q_indices))
        callback_order.append((int(context.twist_index), sector_qs))
        local_action = kwargs["action"]
        maps = {q: kwargs["coordinates"].q_map(i, allocation_gate=lambda *_: None)
                for i, q in enumerate(sector_qs)}
        source_type = task40_v30_selected_q_csr.LiveP6SelectedQContributionSource
        sources = {
            q: source_type(local_action, kwargs["local_h"])
            for q in kwargs["q_indices"]
        }
        operators = {
            q: task40_v30_selected_q_csr.selected_q_operator_identity(
                scientific_input_sha256=scientific_sha,
                profile_identity=profile.identity(),
                ordered_modes=modes,
                q_map=maps[q],
                original_h=kwargs["local_h"],
            )
            for q in kwargs["q_indices"]
        }
        return task40_v30_selected_q_csr.prepare_selected_q_csr_sector(
            sources_by_q=sources,
            q_maps_by_q=maps,
            sector_q_indices=sector_qs,
            twist_index=int(context.twist_index),
            trace_rows_by_q={q: 1 for q in sector_qs},
            selected_q_indices=tuple(map(int, kwargs["q_indices"])),
            action=local_action,
            volume_action=kwargs["volume_action"],
            comm=MPI.COMM_SELF,
            available_sector_matrices=kwargs["available_sector_matrices"],
            allocation_gate=lambda *_args: None,
            profile=profile.name,
            profile_identity=profile.identity(),
            ordered_modes=modes,
            original_h=kwargs["local_h"],
            scientific_input_sha256=scientific_sha,
            operator_identity_by_q=operators,
            matrix_source_identity_by_q={q: matrix_source_identity for q in sources},
            execution_identity=execution_identity,
            producer_identity_by_q={q: execution_identity for q in sources},
            output_directory=tmp_path / f"prepared_twist{context.twist_index}",
        )

    try:
        task40_v10_p6_yorbit.build_task40_v10_p6_reference_inverse(
            cfg,
            axes,
            allocation_gate=lambda *_args: None,
            profile=profile,
            event=lambda name, facts: events.append((name, dict(facts))),
            share_transform_bank=True,
            mode_inventory=mode_inventory,
            qualified_q_csr_provider=provider,
            qualified_q_csr_identity={
                "scientific_input_sha256": scientific_sha,
                "execution_identity": execution_identity,
                "legacy_q0_identity": {"mode_manifest_sha256": mode_sha},
                "ordered_mode_key_sha256": ordered_mode_sha,
            },
            qualified_q_csr_coverage_phase="sector_preparation_subset",
            qualified_q_csr_preparer=actual_q_preparer,
            sector_first=True,
            late_twist0_owner_preparer=late_twist0_owner_preparer,
            factor_output_directory=str(tmp_path / "factor_bank"),
        )
    except FailBeforeFactor:
        pass
    else:
        raise AssertionError("fixture must stop before numerical factor creation")

    assert callback_order == [(1, (1, 5)), (2, (2, 6)), (3, (3, 7))]
    assert provider_loads == [(0, 0), (4, 0)]
    assert pattern_qs == fill_qs == native_qs == [1, 5, 2, 6, 3, 7]
    names = [name for name, _facts in events]
    durable_index = names.index("task40_v33_sector_products_durable")
    global_mesh_index = names.index("task40_v33_global_mesh_fe_mpc", durable_index)
    global_physical_index = names.index("task40_v33_global_physical_phase")
    assert durable_index < global_mesh_index < global_physical_index
    durable = events[durable_index][1]
    assert durable["q_indices"] == list(range(8))
    assert durable["global_physical_started"] is False
    assert schedule == ["global_mesh", "global_physical"]
    assert len(banks) == 1 and banks[0]._closed is True
    assert late_owner_bank_calls == [banks[0]]
    assert all(owner["local_owner_cleanup_complete"] is True for owner in owner_rows)
    assert [int(entry[0]) for entry in callback_order] == [1, 2, 3]


def _v30_service_payload(tmp_path):
    from src.geometry.task40_nonseparable_plan import (
        TASK40_COMPARISON_GROUP,
        TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT,
        TASK40_Q_ASSEMBLY_ROW_TILE_V17,
        TASK40_V15_REFERENCE_PC_STRATEGY,
    )
    from src.solvers.task40_v20_registry import task40_v20_case

    case = task40_v20_case(profile="task40extra_v20_p6_y_orbit_target_original_ny8_v1")
    return {
        "run_id": case.run_id,
        "comparison_group": TASK40_COMPARISON_GROUP,
        "method": {"kind": "full3d_iterative"},
        "solver": {
            "preconditioner": case.profile,
            "stage": case.solver_stage,
            "task40_reference_pc_strategy": TASK40_V15_REFERENCE_PC_STRATEGY,
            "task40_q_assembly_strategy": TASK40_Q_ASSEMBLY_ROW_TILE_V17,
            "task40_factor_lifecycle_strategy": TASK40_FACTOR_LIFECYCLE_ALL_Q_RESIDENT,
        },
        "derived": {"physical_intermediate_profile": {"identity": case.profile}},
        "execution": {
            "task40_execution_stop_stage": "full",
            "task40_target_heavy_authorized": True,
            "task40_v30_q_csr_binding": {
                "schema": "task40extra.review_v30_q_csr_worker_binding.v1",
                "selector_path": "benchmarks/artifacts/task40extra_0p7nm_engineering/local_v30_wsl/selector.json",
                "selector_sha256": "a" * 64,
            },
            "task40_v30_factor_bank_config": {
                "schema": "task40extra.review_v30_all_q_factor_bank.v1",
                "require_two_strict_rhs": True,
                "second_rhs_formula": "frozen_formula",
                "output_directory": str(tmp_path / "all_q_packets"),
            },
        },
    }


def test_v30_dispatcher_routes_to_reviewed_service(monkeypatch, tmp_path):
    from src.runners import task40_v20_stage_runner
    from src.runners.task038_full3d_iterative import run_full3d_iterative

    payload = _v30_service_payload(tmp_path)
    calls = []
    monkeypatch.setattr(
        task40_v20_stage_runner,
        "run_task40_v20_stage",
        lambda resolved, directory, *, source_sha: calls.append(
            (resolved, directory, source_sha)
        ) or {"routed": True},
    )

    result = run_full3d_iterative(payload, tmp_path / "run", source_sha="b" * 40)

    assert result == {"routed": True}
    assert len(calls) == 1
    assert calls[0][0] is payload
    assert calls[0][2] == "b" * 40


def test_v30_service_stubs_worker_with_frozen_selector_and_factor_config(monkeypatch, tmp_path):
    from src.runners import task40_v20_stage_runner as runner
    from src.runners import task40_v30_contract

    payload = _v30_service_payload(tmp_path)
    case_profile = payload["solver"]["preconditioner"]
    captured = {}
    contract_sha = "e" * 64
    contract = {
        "execution": {"campaign_window_sha256": "f" * 64},
        "preparation": {
            "accepted_q0_donor": {"identity_sha256": "a" * 64},
            "q_csr_worklist": [{"q": 4, "twist_index": 0}],
            "final_all_q_selector_required_at": "P3_all_q_resident_factor_bank",
        },
    }
    monkeypatch.setenv("TASK40_V30_STRICT_EXECUTION", "1")
    monkeypatch.setenv("TASK40_V30_CONTRACT_PATH", str(tmp_path / "contract.json"))
    monkeypatch.setenv("TASK40_V30_CONTRACT_SHA256", contract_sha)
    monkeypatch.setenv("TASK40_V30_EXECUTION_WINDOW_SHA256", "f" * 64)
    monkeypatch.setattr(
        task40_v30_contract,
        "require_authorized_contract",
        lambda *_args, **_kwargs: (contract, contract_sha),
    )
    monkeypatch.setattr(
        runner,
        "_preflight",
        lambda *_args, **_kwargs: (
            {"run_id": payload["run_id"], "input_sha256": "c" * 64},
            None,
            None,
        ),
    )
    monkeypatch.setattr(
        "src.runners.task40_v10_worker.run_task40_v10_p6_reference_worker",
        lambda resolved, directory, **kwargs: captured.update(
            resolved=resolved, directory=directory, kwargs=kwargs
        ) or {"passed": True, "status": "completed", "official_result": False},
    )

    result = runner.run_task40_v20_stage(
        payload, tmp_path / "attempt", source_sha="d" * 40
    )

    assert result["status"] == "completed"
    assert captured["resolved"] is payload
    assert captured["kwargs"]["profile_identity"] == case_profile
    assert captured["kwargs"]["stop_after_stage"] if "stop_after_stage" in captured["kwargs"] else None is None
    assert captured["kwargs"]["v30_q_csr_binding"] == payload["execution"][
        "task40_v30_q_csr_binding"
    ]
    assert captured["kwargs"]["v30_factor_config"] == payload["execution"][
        "task40_v30_factor_bank_config"
    ]
    receipt_path = Path(tmp_path / "attempt" / "v30_worker_service_receipt.json")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["q_csr_selector"] == payload["execution"]["task40_v30_q_csr_binding"]
    assert receipt["factor_bank_schema"] == payload["execution"][
        "task40_v30_factor_bank_config"
    ]["schema"]
