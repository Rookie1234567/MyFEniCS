from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

import src.solvers.task40_v27_saved_q0 as saved_q0
from src.solvers.task40_v27_saved_q0 import (
    SavedQ0ContributionAdapter,
    build_saved_q0_csr_structure,
    fill_saved_q0_csr_values,
    open_saved_q0_csr_from_manifest,
    preflight_saved_q0_csr,
)


_SURFACE_HEADER = struct.Struct("<qQQd")
_VOLUME_MAGIC = b"TASK40V25Q0VOLUME\0"


def _write_surface(path, *, bad_unmapped: bool = False):
    frames = (
        (10, 2.0, [0, 1, 3], [1.0 + 1.0j, 2.0 - 1.0j, 9.0 if bad_unmapped else 0.0], [1, 3], [3.0 + 4.0j, 0.0]),
        (11, 3.0, [2], [5.0 + 2.0j], [2], [6.0j]),
    )
    with path.open("wb") as stream:
        for global_index, h_value, b_rows, b_values, d_rows, d_values in frames:
            stream.write(_SURFACE_HEADER.pack(global_index, len(b_rows), len(d_rows), h_value))
            np.asarray(b_rows, dtype="<i4").tofile(stream)
            np.asarray(b_values, dtype="<c16").tofile(stream)
            np.asarray(d_rows, dtype="<i4").tofile(stream)
            np.asarray(d_values, dtype="<c16").tofile(stream)


def _write_volume(path):
    schur = np.asarray([[4.0 + 1.0j, 1.0 - 2.0j], [2.0 + 3.0j, 5.0 - 1.0j]], dtype=np.complex128)
    expansion = sparse.csr_matrix(
        np.asarray([[1.0, 0.0], [0.5j, 1.0]], dtype=np.complex128)
    )
    with path.open("wb") as stream:
        stream.write(_VOLUME_MAGIC)
        stream.write(struct.pack("<II", 1, 1))
        stream.write(struct.pack("<II", *schur.shape))
        np.asarray(schur, dtype="<c16").tofile(stream)
        stream.write(struct.pack("<iiii", 0, 2, 2, expansion.nnz))
        np.asarray([0, 1], dtype="<i4").tofile(stream)
        np.asarray(expansion.indptr, dtype="<i4").tofile(stream)
        np.asarray(expansion.indices, dtype="<i4").tofile(stream)
        np.asarray(expansion.data, dtype="<c16").tofile(stream)
    return schur, expansion


def _adapter(tmp_path, *, bad_unmapped: bool = False):
    volume = tmp_path / "volume.bin"
    surface = tmp_path / "surface.bin"
    schur, expansion = _write_volume(volume)
    _write_surface(surface, bad_unmapped=bad_unmapped)
    lookup = np.asarray([0, 1, 2, -1], dtype=np.int32)
    local_h = np.asarray([2.0, 3.0], dtype=np.complex128)
    q0_map = sparse.csr_matrix(
        (
            np.asarray([1.0, 1.0, 1.0], dtype=np.complex128),
            (np.asarray([0, 1, 3], dtype=np.int32), np.asarray([0, 1, 2], dtype=np.int32)),
        ),
        shape=(5, 3),
    )
    adapter = SavedQ0ContributionAdapter(
        volume_stream_path=volume,
        surface_stream_path=surface,
        active_lookup=lookup,
        local_h=local_h,
        q0_map=q0_map,
        active_rows=3,
        q0_trace_rows=2,
        q0_port_rows=1,
        expected_cell_count=1,
        expected_class_count=1,
    )
    return adapter, schur, expansion


def test_saved_q0_adapter_replays_volume_surface_and_h_without_q4_placeholder(tmp_path):
    adapter, schur, expansion = _adapter(tmp_path)
    layouts = list(adapter.iter_reduced_contribution_layouts(hhat_block_columns=1))
    labels = [label for _rows, _columns, label in layouts]
    assert labels == [
        "ports/Hhat/0:1",
        "ports/Hhat/1:2",
        "volume/cell/0",
        "direct/C/provider/0",
        "direct/-D/provider/0",
        "direct/C/provider/1",
        "direct/-D/provider/1",
    ]
    # H is numerically diagonal, while its structural layout remains the
    # complete ports-by-port-column-block superset required by V26 counts.
    np.testing.assert_array_equal(layouts[0][0], np.asarray([3, 4], dtype=np.int32))
    np.testing.assert_array_equal(layouts[0][1], np.asarray([3], dtype=np.int32))

    requests = []
    blocks = list(
        adapter.iter_reduced_contributions(
            allocation_gate=lambda label, facts: requests.append((label, dict(facts))),
            hhat_block_columns=1,
        )
    )
    by_label = {label: (rows, columns, values) for rows, columns, values, label in blocks}
    np.testing.assert_allclose(
        by_label["volume/cell/0"][2],
        expansion.conjugate().T @ schur @ expansion,
        rtol=0.0,
        atol=1e-14,
    )
    np.testing.assert_array_equal(by_label["ports/Hhat/0:1"][2], np.asarray([[2.0], [0.0]]))
    np.testing.assert_array_equal(by_label["ports/Hhat/1:2"][2], np.asarray([[0.0], [3.0]]))
    np.testing.assert_array_equal(by_label["direct/C/provider/0"][0], np.asarray([0, 1], dtype=np.int32))
    np.testing.assert_array_equal(
        by_label["direct/C/provider/0"][2].reshape(-1),
        np.asarray([1.0 + 1.0j, 2.0 - 1.0j]),
    )
    # The D block keeps the ordinary transpose convention and only changes sign.
    np.testing.assert_array_equal(
        by_label["direct/-D/provider/0"][2],
        np.asarray([[-3.0 - 4.0j]], dtype=np.complex128),
    )
    assert all("q_map_count" in facts for _label, facts in requests)
    assert not any("q4" in label.lower() for label in labels)


def test_saved_q0_adapter_rejects_nonzero_unmapped_surface_rows(tmp_path):
    adapter, _schur, _expansion = _adapter(tmp_path, bad_unmapped=True)
    with pytest.raises(ValueError, match="nonzero saved q0 B row has no active"):
        list(adapter.iter_reduced_contribution_layouts(hhat_block_columns=1))


def test_saved_q0_source_binding_uses_nested_verified_producer_payload_identity(
    monkeypatch, tmp_path
):
    adapter, _schur, _expansion = _adapter(tmp_path)
    donor_import = {
        "producer_identity": {
            "payloads": [
                {"path": "volume.bin", "bytes": adapter.volume_stream_path.stat().st_size, "sha256": "a" * 64},
                {"path": "surface.bin", "bytes": adapter.surface_stream_path.stat().st_size, "sha256": "b" * 64},
            ]
        },
        "saved_replay_manifest": {"sha256": "c" * 64},
        "native_recovery_manifest": {"sha256": "d" * 64},
    }

    def unexpected_hash(_path):
        pytest.fail("a verified donor stream must not be hashed again while binding CSR")

    monkeypatch.setattr(saved_q0, "_sha256_file", unexpected_hash)
    bindings = saved_q0._adapter_source_bindings(adapter, donor_import)
    assert bindings["volume_stream"]["sha256"] == "a" * 64
    assert bindings["surface_stream"]["sha256"] == "b" * 64


def test_saved_q0_v17_build_persists_q0_only_structure_and_restartable_values(
    monkeypatch, tmp_path
):
    adapter, _schur, _expansion = _adapter(tmp_path)
    row_columns = [set() for _ in range(adapter.q0_map.shape[1])]
    for rows, columns, _label in adapter.iter_reduced_contribution_layouts(
        hhat_block_columns=1
    ):
        left = adapter.q0_map[np.asarray(rows, dtype=np.int32), :].tocsr()
        right = adapter.q0_map[np.asarray(columns, dtype=np.int32), :].tocsr()
        left_support = np.unique(left.indices)
        right_support = np.unique(right.indices)
        for row in left_support:
            row_columns[int(row)].update(map(int, right_support))
    expected_counts = np.asarray([len(columns) for columns in row_columns], dtype=np.int64)
    expected_offsets = np.zeros(len(expected_counts) + 1, dtype=np.int64)
    expected_offsets[1:] = np.cumsum(expected_counts, dtype=np.int64)
    gates = []

    def allocation_gate(label, facts):
        gates.append((label, dict(facts)))

    preflight = preflight_saved_q0_csr(
        adapter,
        expected_row_counts=expected_counts,
        expected_offsets=expected_offsets,
        allocation_gate=allocation_gate,
    )
    assert preflight["expected_nnz"] == int(expected_offsets[-1])
    assert gates[0][1]["q_map_count"] == 1
    assert gates[0][1]["all_known_future_owner_reserves_included"] is True

    output = tmp_path / "saved-q0-csr"
    donor_identity = {
        "producer_identity": {
            "producer_run_id": "synthetic-v26-fixture",
            "payloads": [
                {
                    "path": adapter.volume_stream_path.name,
                    "bytes": adapter.volume_stream_path.stat().st_size,
                    "sha256": "a" * 64,
                },
                {
                    "path": adapter.surface_stream_path.name,
                    "bytes": adapter.surface_stream_path.stat().st_size,
                    "sha256": "b" * 64,
                },
            ],
        },
        "saved_replay_manifest": {"sha256": "c" * 64},
        "native_recovery_manifest": {"sha256": "d" * 64},
        "row_structure_witness": {"sha256": "e" * 64},
    }
    structure_identity = {
        "donor_identity": donor_identity,
        "execution": {"source_sha": "source-a", "window_sha256": "v27-fixture"},
    }
    continuation_identity = {
        "donor_identity": donor_identity,
        "execution": {"source_sha": "source-b", "window_sha256": "v27-fixture"},
    }

    original_hash = saved_q0._sha256_file
    donor_stream_paths = {
        adapter.volume_stream_path.resolve(),
        adapter.surface_stream_path.resolve(),
    }

    def no_donor_rehash(path):
        if Path(path).resolve() in donor_stream_paths:
            pytest.fail("CSR structure/fill must reuse the verified donor payload hashes")
        return original_hash(path)

    monkeypatch.setattr(saved_q0, "_sha256_file", no_donor_rehash)
    blocks, structure, manifest_path = build_saved_q0_csr_structure(
        adapter,
        output_directory=output,
        expected_row_counts=expected_counts,
        expected_offsets=expected_offsets,
        allocation_gate=allocation_gate,
        source_identity=structure_identity,
    )
    assert structure["status"] == "STRUCTURE_COMPLETE_VALUES_PENDING"
    assert structure["q_map_count"] == 1
    assert structure["source_bindings"]["volume_stream"]["sha256"] == "a" * 64
    assert structure["source_bindings"]["surface_stream"]["sha256"] == "b" * 64
    assert Path(structure["support_routes"]["path"]).is_file()
    assert blocks[(0, 0)].nnz == int(expected_offsets[-1])
    assert np.all(blocks[(0, 0)].data == 0.0)

    def interrupted_gate(label, facts):
        allocation_gate(label, facts)
        if label.endswith("volume/cell/0"):
            raise RuntimeError("fixture interruption after a partial numeric contribution")

    with pytest.raises(RuntimeError, match="fixture interruption"):
        fill_saved_q0_csr_values(
            adapter,
            manifest_path=manifest_path,
            allocation_gate=interrupted_gate,
            source_identity=continuation_identity,
        )
    interrupted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert interrupted["status"] == "NUMERIC_FILL_INCOMPLETE"
    partial_data = np.load(
        interrupted["csr_artifacts"]["data"]["path"], mmap_mode="r", allow_pickle=False
    )
    assert np.any(partial_data != 0.0)

    q0_size = adapter.q0_map.shape[1]
    expected = np.zeros((q0_size, q0_size), dtype=np.complex128)
    for rows, columns, values, _label in adapter.iter_reduced_contributions(
        allocation_gate=lambda *_args, **_kwargs: None,
        hhat_block_columns=1,
    ):
        expected += (
            adapter.q0_map[rows, :].toarray().conjugate().T
            @ values
            @ adapter.q0_map[columns, :].toarray()
        )
    matrix, completed = fill_saved_q0_csr_values(
        adapter,
        manifest_path=manifest_path,
        allocation_gate=allocation_gate,
        source_identity=continuation_identity,
    )
    assert completed["status"] == "COMPLETE_CSR"
    assert completed["numeric_pass"]["numeric_facts"]["stored_structural_slots"] == matrix.nnz
    assert completed["numeric_pass"]["numeric_facts"]["numeric_nonzero_entries"] > 0
    assert completed["source_identity"]["execution"]["source_sha"] == "source-a"
    assert completed["numeric_fill_identity"]["execution"]["source_sha"] == "source-b"
    assert matrix.has_canonical_format and matrix.has_sorted_indices
    np.testing.assert_allclose(matrix.toarray(), expected, rtol=0.0, atol=1e-14)
    del matrix
    reopened, readback_manifest = open_saved_q0_csr_from_manifest(manifest_path)
    assert readback_manifest["status"] == "COMPLETE_CSR"

    def reaches_memmap_owner(array):
        current = array
        while current is not None:
            if isinstance(current, np.memmap):
                return True
            current = getattr(current, "base", None)
        return False

    assert reaches_memmap_owner(reopened.data)
    assert reaches_memmap_owner(reopened.indices)
    assert reaches_memmap_owner(reopened.indptr)
    np.testing.assert_allclose(reopened.toarray(), expected, rtol=0.0, atol=1e-14)

