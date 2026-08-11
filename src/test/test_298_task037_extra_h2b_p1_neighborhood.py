from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import gc
import json
import weakref

import numpy as np
import pytest

from src.solvers.hcurl_r2_constrained_local_block import (
    build_h2a_r2_cell_expansion,
)
from src.solvers.hcurl_r2_factor_store import (
    H2AR2CellReference,
    H2AR2ClassInput,
    build_h2a_r2_factor_store,
    load_h2a_r2_factor_store,
)
from src.solvers.hcurl_h2b_p1_factor_store import (
    H2B_P1_ANCHOR_SOURCE_LABELS,
    build_h2b_p1_class_block_authority,
    H2BP1FactorLedger,
    canonical_h2b_p1_neighborhood_key,
    discover_h2b_p1_neighborhoods,
    h2b_p1_live_set_audit,
    measure_h2b_p1_anchor_sources,
    stream_h2b_p1_neighborhood,
)
from src.solvers.hcurl_h2b_block_smoother import factorize_h2b_p0_patch


ROOT = Path(__file__).resolve().parents[2]
R2_MANIFEST = ROOT / (
    "benchmarks/artifacts/task037_extra_development/"
    "h2a_r2_da8ddbb_run1/factor_store/manifest.json"
)
R0_RECORD = ROOT / (
    "benchmarks/cases/101_task37_extra_development/records/"
    "h2a_class_discovery.json"
)
P0_RECORD = ROOT / (
    "benchmarks/cases/101_task37_extra_development/records/"
    "h2b_row_complete_patch_exactclass_v4.json"
)


class _IndexMap:
    def __init__(self, offset: int):
        self.offset = int(offset)

    def local_to_global(self, rows):
        return np.asarray(rows, dtype=np.int64) + self.offset


def _expansion(offset: int, coefficient: complex):
    block = SimpleNamespace(
        slave_local_dofs=(1,),
        slave_global_dofs=(offset + 1,),
        master_global_dofs=(offset, offset + 2),
        coefficient_transform=np.asarray([[1.0 + 0.0j, coefficient]], dtype=np.complex128),
        kind="x",
    )
    return build_h2a_r2_cell_expansion(
        (block,),
        (0, 1, 2),
        _IndexMap(offset),
        index_map_bs=1,
        phase_x=1.0 + 0.0j,
        phase_y=1.0 + 0.0j,
    )


def _class_inventory(material_b: str = "dielectric"):
    return [
        {
            "class_id": 0,
            "class_key_sha256": "a" * 64,
            "constraint_pattern_sha256": "c" * 64,
            "material_tag": "metal",
            "material_identity": {"tag": "metal", "epsilon": 1.0},
            "cell_widths": [0.5, 0.5, 0.5],
            "orientation": [1, 1, -1],
            "constraint_pattern_entry_count": 1,
            "constraint_pattern_kinds": ["x"],
        },
        {
            "class_id": 1,
            "class_key_sha256": "b" * 64,
            "constraint_pattern_sha256": "d" * 64,
            "material_tag": material_b,
            "material_identity": {"tag": material_b, "epsilon": 2.0},
            "cell_widths": [0.5, 0.5, 0.5],
            "orientation": [1, -1, -1],
            "constraint_pattern_entry_count": 1,
            "constraint_pattern_kinds": ["x"],
        },
    ]


def _build_store(
    class1_coefficient: complex = 0.2 + 0.3j,
    *,
    shared_numeric: bool = False,
):
    expansion0 = _expansion(0, 0.2 + 0.1j)
    expansion1 = _expansion(100, class1_coefficient)
    matrix0 = np.asarray(
        ((3.0 + 0.0j, 1.0 + 0.2j), (1.0 - 0.2j, 2.0 + 0.0j)),
        dtype=np.complex128,
        order="C",
    )
    matrix1 = (
        matrix0.copy()
        if shared_numeric
        else np.asarray(
            ((2.5 + 0.0j, 0.3 - 0.1j), (0.3 + 0.1j, 1.8 + 0.0j)),
            dtype=np.complex128,
            order="C",
        )
    )
    store = build_h2a_r2_factor_store(
        (
            H2AR2ClassInput(
                0,
                "a" * 64,
                "c" * 64,
                expansion0.pattern_sha256,
                expansion0,
                matrix0,
            ),
            H2AR2ClassInput(
                1,
                "b" * 64,
                "d" * 64,
                expansion1.pattern_sha256,
                expansion1,
                matrix1,
            ),
        ),
        (
            H2AR2CellReference(0, np.asarray((10, 20), dtype=np.int64)),
            H2AR2CellReference(0, np.asarray((10, 30), dtype=np.int64)),
            H2AR2CellReference(1, np.asarray((10, 40), dtype=np.int64)),
            H2AR2CellReference(1, np.asarray((50, 60), dtype=np.int64)),
        ),
        identity={"source_identity": {"commit": "a" * 40}},
        task037_extra_h2a_r2=True,
    )
    return store, _class_inventory(), (matrix0, matrix1)


def _discover(store, inventory=None):
    return discover_h2b_p1_neighborhoods(
        store.cells,
        store.classes,
        _class_inventory() if inventory is None else inventory,
        {"operator": "B0", "scalar_type": "complex128"},
        task037_extra_h2b=True,
    )


def test_p1_reconstruction_is_fresh_deterministic_and_row_renumber_invariant():
    store, inventory, matrices = _build_store()
    first = store.reconstruct_numeric_matrix(0)
    expected = first.copy()
    first[0, 0] += 4.0
    assert np.array_equal(store.reconstruct_numeric_matrix(0), expected)
    assert np.all(np.isfinite(expected))
    assert np.linalg.norm(expected - matrices[0]) / np.linalg.norm(matrices[0]) <= 1.0e-14

    discovered = _discover(store, inventory)
    shifted = tuple(
        H2AR2CellReference(
            cell.class_id, cell.independent_global_rows + 1000
        )
        for cell in store.cells
    )
    shifted_discovered = discover_h2b_p1_neighborhoods(
        shifted,
        store.classes,
        inventory,
        {"operator": "B0", "scalar_type": "complex128"},
        task037_extra_h2b=True,
    )
    assert shifted_discovered["neighborhood_digest"] == discovered["neighborhood_digest"]


def test_p1_neighborhood_key_binds_incidence_mpc_material_and_operator():
    store, inventory, _matrices = _build_store()
    base_key = canonical_h2b_p1_neighborhood_key(
        0,
        store.cells,
        store.classes,
        inventory,
        {"operator": "B0"},
        task037_extra_h2b=True,
    )[0]
    changed_cells = list(store.cells)
    changed_cells[1] = H2AR2CellReference(0, np.asarray((70, 30), dtype=np.int64))
    assert canonical_h2b_p1_neighborhood_key(
        0, changed_cells, store.classes, inventory, {"operator": "B0"}, task037_extra_h2b=True
    )[0] != base_key

    material = _class_inventory(material_b="different")
    assert canonical_h2b_p1_neighborhood_key(
        0, store.cells, store.classes, material, {"operator": "B0"}, task037_extra_h2b=True
    )[0] != base_key
    orientation = _class_inventory()
    orientation[1]["orientation"] = [1, 1, 1]
    assert canonical_h2b_p1_neighborhood_key(
        0, store.cells, store.classes, orientation, {"operator": "B0"}, task037_extra_h2b=True
    )[0] != base_key
    assert canonical_h2b_p1_neighborhood_key(
        0, store.cells, store.classes, inventory, {"operator": "different"}, task037_extra_h2b=True
    )[0] != base_key

    changed_store, changed_inventory, _ = _build_store(0.2 + 0.4j)
    assert canonical_h2b_p1_neighborhood_key(
        0,
        changed_store.cells,
        changed_store.classes,
        changed_inventory,
        {"operator": "B0"},
        task037_extra_h2b=True,
    )[0] != base_key


def test_p1_stream_matches_direct_constrained_cell_scatter_and_reconstructs_once():
    store, inventory, matrices = _build_store()
    discovered = _discover(store, inventory)
    neighborhood = next(
        item for item in discovered["neighborhoods"] if item.representative_cell == 0
    )
    authority = build_h2b_p1_class_block_authority(
        store, task037_extra_h2b=True
    )
    assert authority.audit["reconstruction_count"] == 2
    assert authority.audit["retained_payload_bytes"] == sum(
        authority.audit["retained_payload_components"].values()
    )
    with pytest.raises(ValueError):
        authority.matrix_for_factor(0)[0, 0] = 0.0
    cell_references = store.cells
    del store
    gc.collect()
    streamed = stream_h2b_p1_neighborhood(
        neighborhood, cell_references, authority, task037_extra_h2b=True
    )
    reference = np.zeros_like(streamed["matrix"])
    patch_index = {int(row): i for i, row in enumerate(neighborhood.patch_rows)}
    for ordinal in neighborhood.touching_cell_ordinals:
        cell = cell_references[ordinal]
        positions = [patch_index.get(int(row), -1) for row in cell.independent_global_rows]
        selected = [i for i, position in enumerate(positions) if position >= 0]
        target = [positions[i] for i in selected]
        reference[np.ix_(target, target)] += matrices[cell.class_id][np.ix_(selected, selected)]
    assert streamed["r2_factor_reconstruction_count"] == 2
    assert streamed["r2_factor_authority_bytes"] == authority.audit[
        "retained_payload_bytes"
    ]
    assert np.linalg.norm(streamed["matrix"] - reference) / np.linalg.norm(reference) <= 1.0e-14
    assert streamed["max_live_patch_matrix_count"] == 1
    assert streamed["per_cell_dense_tensor"] is False
    again = stream_h2b_p1_neighborhood(
        neighborhood, cell_references, authority, task037_extra_h2b=True
    )
    assert again["r2_factor_reconstruction_count"] == 2
    assert np.array_equal(again["matrix"], streamed["matrix"])


def test_p1_authority_builder_consumes_one_reconstruction_at_a_time(monkeypatch):
    store, _inventory, _matrices = _build_store()
    events = []
    original = store.reconstruct_numeric_matrix

    class _TrackedArray(np.ndarray):
        pass

    def counted_reconstruction(factor_id):
        events.append(("requested", factor_id))
        matrix = original(factor_id).view(_TrackedArray)
        weakref.finalize(matrix, events.append, ("released", factor_id))
        return matrix

    monkeypatch.setattr(store, "reconstruct_numeric_matrix", counted_reconstruction)
    authority = build_h2b_p1_class_block_authority(
        store, task037_extra_h2b=True
    )
    gc.collect()

    assert events.index(("released", 0)) < events.index(("requested", 1))
    assert events.index(("requested", 1)) < events.index(("released", 1))
    assert authority.audit["reconstruction_count"] == 2
    assert all(not matrix.flags.writeable for matrix in authority.reconstructed_matrices)


def test_p1_numeric_order_is_row_and_enumeration_invariant():
    store, inventory, _matrices = _build_store()
    authority = build_h2b_p1_class_block_authority(
        store, task037_extra_h2b=True
    )
    discovered = _discover(store, inventory)
    neighborhood = next(
        item for item in discovered["neighborhoods"] if item.representative_cell == 0
    )
    base = stream_h2b_p1_neighborhood(
        neighborhood, store.cells, authority, task037_extra_h2b=True
    )

    shifted_cells = tuple(
        H2AR2CellReference(cell.class_id, cell.independent_global_rows + 1000)
        for cell in store.cells
    )
    shifted = discover_h2b_p1_neighborhoods(
        shifted_cells,
        store.classes,
        inventory,
        {"operator": "B0", "scalar_type": "complex128"},
        task037_extra_h2b=True,
    )
    shifted_neighborhood = next(
        item for item in shifted["neighborhoods"] if item.representative_cell == 0
    )
    shifted_stream = stream_h2b_p1_neighborhood(
        shifted_neighborhood, shifted_cells, authority, task037_extra_h2b=True
    )

    reordered_cells = tuple(store.cells[index] for index in (0, 2, 1, 3))
    reordered = _discover(SimpleNamespace(cells=reordered_cells, classes=store.classes))
    reordered_neighborhood = next(
        item for item in reordered["neighborhoods"] if item.representative_cell == 0
    )
    reordered_stream = stream_h2b_p1_neighborhood(
        reordered_neighborhood,
        reordered_cells,
        authority,
        task037_extra_h2b=True,
    )

    assert neighborhood.key_sha256 == shifted_neighborhood.key_sha256
    assert neighborhood.key_sha256 == reordered_neighborhood.key_sha256
    assert set(neighborhood.numeric_accumulation_order) == set(
        neighborhood.touching_cell_ordinals
    )
    assert np.array_equal(base["matrix"], shifted_stream["matrix"])
    assert np.array_equal(base["matrix"], reordered_stream["matrix"])
    assert base["matrix_sha256"] == shifted_stream["matrix_sha256"]
    assert base["matrix_sha256"] == reordered_stream["matrix_sha256"]


def test_p1_numeric_sha_dedup_survives_class_metadata_but_not_matrix_change():
    shared_store, inventory, _matrices = _build_store(shared_numeric=True)
    shared_authority = build_h2b_p1_class_block_authority(
        shared_store, task037_extra_h2b=True
    )
    assert shared_authority.audit["factor_count"] == 1
    shared_discovered = _discover(shared_store, inventory)
    shared_neighborhood = next(
        item
        for item in shared_discovered["neighborhoods"]
        if item.representative_cell == 0
    )
    shared_stream = stream_h2b_p1_neighborhood(
        shared_neighborhood,
        shared_store.cells,
        shared_authority,
        task037_extra_h2b=True,
    )

    changed_inventory = _class_inventory()
    changed_inventory[1]["orientation"] = [1, 1, 1]
    changed_discovered = _discover(shared_store, changed_inventory)
    changed_neighborhood = next(
        item
        for item in changed_discovered["neighborhoods"]
        if item.representative_cell == 0
    )
    changed_stream = stream_h2b_p1_neighborhood(
        changed_neighborhood,
        shared_store.cells,
        shared_authority,
        task037_extra_h2b=True,
    )
    assert changed_neighborhood.key_sha256 != shared_neighborhood.key_sha256
    assert np.array_equal(shared_stream["matrix"], changed_stream["matrix"])

    ledger = H2BP1FactorLedger(task037_extra_h2b=True)
    assert ledger.accept(shared_stream["matrix"], task037_extra_h2b=True) == 0
    assert ledger.accept(changed_stream["matrix"], task037_extra_h2b=True) == 0

    different_store, different_inventory, _matrices = _build_store()
    different_authority = build_h2b_p1_class_block_authority(
        different_store, task037_extra_h2b=True
    )
    different_discovered = _discover(different_store, different_inventory)
    different_neighborhood = next(
        item
        for item in different_discovered["neighborhoods"]
        if item.representative_cell == 0
    )
    different_stream = stream_h2b_p1_neighborhood(
        different_neighborhood,
        different_store.cells,
        different_authority,
        task037_extra_h2b=True,
    )
    assert not np.array_equal(shared_stream["matrix"], different_stream["matrix"])
    assert ledger.accept(different_stream["matrix"], task037_extra_h2b=True) == 1


def test_p1_real_r2_mapping_closes_252_cells_and_84_neighborhoods():
    if not R2_MANIFEST.exists() or not R0_RECORD.exists():
        pytest.skip("frozen R2/R0 authority artifacts are unavailable")
    store = load_h2a_r2_factor_store(R2_MANIFEST, task037_extra_h2a_r2=True)
    r0 = json.loads(R0_RECORD.read_text(encoding="utf-8"))
    inventory = r0["measurements"]["p6_h10"]["class_inventory"]
    discovered = discover_h2b_p1_neighborhoods(
        store.cells,
        store.classes,
        inventory,
        {"operator": "B0", "scalar_type": "complex128"},
        task037_extra_h2b=True,
    )
    assert discovered["cell_count"] == 252
    assert discovered["unique_neighborhood_count"] == 84
    assert discovered["cell_neighborhood_ids"].size == 252
    assert {int(cell.class_id) for cell in store.cells} == set(range(24))
    assert all(cell.independent_global_rows.size == 882 for cell in store.cells)
    assert discovered["global_matrix_materialized"] is False
    assert discovered["global_constraint_matrix_materialized"] is False

    p0 = json.loads(P0_RECORD.read_text(encoding="utf-8"))
    assert p0["authority"]["r2_factor_manifest_sha256"]
    assert p0["measurements"]["selection"]["class_id"] == 3
    assert p0["measurements"]["patch"]["touching_cell_count"] == 19


def test_p1_factor_ledger_exact_dedup_ceiling_and_live_set_accounting():
    store, _inventory, matrices = _build_store()
    ledger = H2BP1FactorLedger(task037_extra_h2b=True)
    assert ledger.accept(matrices[0], task037_extra_h2b=True) == 0
    assert ledger.accept(matrices[0].copy(), task037_extra_h2b=True) == 0
    assert ledger.accept(matrices[1], task037_extra_h2b=True) == 1
    audit = ledger.audit(
        neighborhood_count=84,
        cell_count=252,
        metadata_bytes=100,
        class_expansion_sparse_bytes=200,
        cell_reference_bytes=300,
        neighborhood_mapping_bytes=400,
        task037_extra_h2b=True,
    )
    assert audit["unique_factor_count"] == 2
    assert audit["factor_plus_metadata_bytes"] == sum(
        audit["retained_payload_components"].values()
    )
    assert audit["finite"] is True and audit["deterministic"] is True
    assert audit["per_cell_factor_count"] == 0
    assert audit["per_cell_dense_tensor"] is False
    assert audit["global_matrix_materialized"] is False
    assert audit["slab_factor_count"] == 0
    dense_bytes = 882 * 882 * 16
    pivots_bytes = 882 * 4
    int64_pivots_bytes = 882 * 8
    live = h2b_p1_live_set_audit(
        reconstruction_stage={
            "mesh_action_runtime_bytes": 552_968_708,
            "r2_lu_bytes": 199_204_992,
            "reconstructed_cache_bytes": 199_148_544,
            "reconstruction_lower_workspace_bytes": dense_bytes,
            "reconstruction_upper_workspace_bytes": dense_bytes,
            "reconstruction_permuted_workspace_bytes": dense_bytes,
            "reconstruction_output_workspace_bytes": dense_bytes,
            "reconstruction_pivots_bytes": pivots_bytes,
            "authority_copy_source_bytes": dense_bytes,
            "authority_copy_destination_bytes": dense_bytes,
            "metadata_work_bytes": 50_000_000,
            "runtime_reserve_bytes": 250_000_000,
        },
        factor_stage={
            "mesh_action_runtime_bytes": 552_968_708,
            "reconstructed_cache_bytes": 199_148_544,
            "accepted_factor_bytes": 398_409_984,
            "current_patch_matrix_bytes": dense_bytes,
            "current_lu_workspace_bytes": 12_450_312,
            "factorization_original_copy_bytes": dense_bytes,
            "factorization_first_lu_bytes": 12_450_312,
            "factorization_repeated_lu_bytes": 12_450_312,
            "factorization_lower_workspace_bytes": dense_bytes,
            "factorization_upper_workspace_bytes": dense_bytes,
            "factorization_reconstructed_workspace_bytes": dense_bytes,
            "factorization_pivots_workspace_bytes": int64_pivots_bytes,
            "factorization_condition_workspace_bytes": dense_bytes,
            "metadata_work_bytes": 50_000_000,
            "runtime_reserve_bytes": 250_000_000,
        },
        task037_extra_h2b=True,
    )
    assert live["stages"]["reconstruction"]["predicted_live_set_bytes"] == 1_326_006_476
    assert live["stages"]["factor"]["predicted_live_set_bytes"] == 1_562_565_932
    assert live["predicted_live_set_bytes"] == 1_562_565_932
    assert live["predicted_live_set_gate"] is True
    assert live["workspace_accounting"]["reconstruction_internal_dense_matrices"] == 4
    assert live["workspace_accounting"]["authority_copy_dense_matrices"] == 2
    assert live["workspace_accounting"]["authority_copy_phase_mutually_exclusive"] is True
    assert live["r2_store_released_before_factor_stage"] is True

    ceiling = H2BP1FactorLedger(task037_extra_h2b=True)
    for index in range(32):
        matrix = np.asarray([[2.0 + index]], dtype=np.complex128, order="C")
        assert ceiling.accept(matrix, task037_extra_h2b=True) == index
    with pytest.raises(ValueError, match="unique numeric factor limit"):
        ceiling.accept(np.asarray([[99.0 + 0.0j]], dtype=np.complex128), task037_extra_h2b=True)


def test_p1_anchor_source_oracle_requires_authority_and_uses_five_fixed_labels():
    matrix = np.asarray(
        ((3.0 + 0.0j, 0.2 - 0.1j, 0.0), (0.2 + 0.1j, 2.0, 0.1), (0.0, 0.1, 1.5)),
        dtype=np.complex128,
        order="C",
    )
    factor = factorize_h2b_p0_patch(matrix, task037_extra_h2b=True)
    rhs = {
        label: np.asarray(
            [1.0 + 0.1j * i for i in range(3)], dtype=np.complex128
        )
        for label in H2B_P1_ANCHOR_SOURCE_LABELS
    }

    def action(source, target):
        target[:] = matrix @ source

    authority = {
        "r0_source": "a" * 40,
        "r1_source": "b" * 40,
        "r2_factor_manifest_sha256": "c" * 64,
        "r2_record_sha256": "d" * 64,
        "r2_record_evidence_sha256": "e" * 64,
    }
    result = measure_h2b_p1_anchor_sources(
        rhs,
        matrix,
        factor,
        np.arange(3, dtype=np.int64),
        action,
        authority=authority,
        task037_extra_h2b=True,
    )
    assert result["source_order"] == list(H2B_P1_ANCHOR_SOURCE_LABELS)
    assert result["finite"] is True
    assert all(item["finite"] is True for item in result["sources"].values())
    assert all(item["exact_action_relative_error"] <= 1.0e-11 for item in result["sources"].values())
    with pytest.raises(ValueError, match="authority"):
        measure_h2b_p1_anchor_sources(
            rhs,
            matrix,
            factor,
            np.arange(3, dtype=np.int64),
            action,
            authority={"r0_source": "a" * 40},
            task037_extra_h2b=True,
        )
