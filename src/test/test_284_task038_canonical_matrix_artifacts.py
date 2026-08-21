"""Pure contracts for the streaming canonical matrix artifact helper."""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI

from benchmarks.canonical_matrix_artifacts import (
    compare_canonical_matrices,
    read_canonical_matrix_manifest,
    write_canonical_matrix_shard,
)


def _columns(first: int, last: int):
    def column(index: int):
        return [
            (("row", row), complex((row + 1) * (index + 1), row - index))
            for row in range(first, last)
        ]

    return column


def _write_single(root: Path, first: int, last: int) -> dict:
    return write_canonical_matrix_shard(
        root,
        role="synthetic_full_fe_dual_matrix",
        column_count=4,
        columns=_columns(first, last),
        extractor_audit={"role": "full_fe_dual", "numeric_allgather": False},
        comm=MPI.COMM_SELF,
    )


def _combine_two_shards(root: Path, left: Path, right: Path) -> Path:
    root.mkdir()
    left_manifest = json.loads(
        (left / "matrix.manifest.json").read_text(encoding="utf-8")
    )
    right_manifest = json.loads(
        (right / "matrix.manifest.json").read_text(encoding="utf-8")
    )
    descriptors = []
    for rank, source, manifest in ((0, left, left_manifest), (1, right, right_manifest)):
        descriptor = dict(manifest["per_rank_shards"][0])
        descriptor["rank"] = rank
        key_name = f"rank_{rank:04d}.keys.jsonl"
        value_name = f"rank_{rank:04d}.values.npy"
        shutil.copy2(
            source / descriptor["key_filename"],
            root / key_name,
        )
        shutil.copy2(
            source / descriptor["value_filename"],
            root / value_name,
        )
        descriptor["key_filename"] = key_name
        descriptor["value_filename"] = value_name
        descriptors.append(descriptor)
    manifest = dict(left_manifest)
    manifest["mpi_size"] = 2
    manifest["per_rank_shards"] = descriptors
    manifest["global_packet_count"] = sum(
        item["local_packet_count"] for item in descriptors
    )
    manifest["global_duplicate_count"] = 0
    (root / "matrix.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return root / "matrix.manifest.json"


def _update_value_sha(manifest_path: Path, rank: int = 0) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    descriptor = manifest["per_rank_shards"][rank]
    value_path = manifest_path.parent / descriptor["value_filename"]
    descriptor["value_file_sha256"] = hashlib.sha256(
        value_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="artifact contract uses MPI.COMM_SELF",
)
def test_canonical_matrix_streaming_sharding_mmap_and_prefix_compare(tmp_path: Path):
    one_root = tmp_path / "one"
    left_root = tmp_path / "left"
    right_root = tmp_path / "right"
    one_result = _write_single(one_root, 0, 6)
    _write_single(left_root, 0, 3)
    _write_single(right_root, 3, 6)
    two_manifest = _combine_two_shards(tmp_path / "two", left_root, right_root)

    manifest = read_canonical_matrix_manifest(one_result["manifest_path"])
    assert manifest["global_packet_count"] == 6
    assert manifest["global_duplicate_count"] == 0
    descriptor = manifest["per_rank_shards"][0]
    assert descriptor["value_shape"] == [6, 4]
    values = np.load(
        one_root / descriptor["value_filename"], mmap_mode="r", allow_pickle=False
    )
    assert isinstance(values, np.memmap)
    assert values.shape == (6, 4)
    del values

    exact = compare_canonical_matrices(
        one_result["manifest_path"],
        two_manifest,
        prefixes=(1, 2, 4),
    )
    assert exact["passed"] is True
    assert exact["key_set_exact"] is True
    assert exact["left_mpi_size"] == 1
    assert exact["right_mpi_size"] == 2
    assert all(item["relative_l2"] == 0.0 for item in exact["prefixes"].values())

    perturbed_root = tmp_path / "perturbed"
    shutil.copytree(one_root, perturbed_root)
    perturbed_manifest = perturbed_root / "matrix.manifest.json"
    perturbed_data = np.lib.format.open_memmap(
        perturbed_root / descriptor["value_filename"], mode="r+"
    )
    perturbed_data[0, 0] += 1.0e-13
    perturbed_data.flush()
    del perturbed_data
    _update_value_sha(perturbed_manifest)
    near = compare_canonical_matrices(
        one_result["manifest_path"], perturbed_manifest, prefixes=(1, 2, 4)
    )
    assert near["passed"] is True
    assert near["prefixes"]["1"]["max_abs"] > 0.0

    far_root = tmp_path / "far"
    shutil.copytree(one_root, far_root)
    far_manifest = far_root / "matrix.manifest.json"
    far_data = np.lib.format.open_memmap(
        far_root / descriptor["value_filename"], mode="r+"
    )
    far_data[0, 0] += 1.0e-8
    far_data.flush()
    del far_data
    _update_value_sha(far_manifest)
    far = compare_canonical_matrices(
        one_result["manifest_path"], far_manifest, prefixes=(1, 2, 4)
    )
    assert far["passed"] is False
    assert far["prefixes"]["1"]["relative_l2"] > far["prefixes"]["1"]["limit"]

    with pytest.raises(RuntimeError, match="FileExistsError"):
        _write_single(one_root, 0, 6)


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="artifact contract uses MPI.COMM_SELF",
)
def test_canonical_matrix_malformed_artifacts_fail_closed(tmp_path: Path):
    base = tmp_path / "base"
    _write_single(base, 0, 4)
    base_manifest = base / "matrix.manifest.json"

    mutations = ("missing", "duplicate", "hash", "shape", "nonfinite")
    for mutation in mutations:
        root = tmp_path / mutation
        shutil.copytree(base, root)
        manifest_path = root / "matrix.manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        descriptor = manifest["per_rank_shards"][0]
        key_path = root / descriptor["key_filename"]
        value_path = root / descriptor["value_filename"]
        if mutation == "missing":
            key_path.unlink()
        elif mutation == "duplicate":
            lines = key_path.read_bytes().splitlines()
            lines[1] = lines[0]
            key_path.write_bytes(b"\n".join(lines) + b"\n")
            descriptor["key_file_sha256"] = hashlib.sha256(
                key_path.read_bytes()
            ).hexdigest()
            descriptor["key_file_bytes"] = key_path.stat().st_size
            descriptor["local_duplicate_count"] = 1
            manifest["global_duplicate_count"] = 1
        elif mutation == "hash":
            payload = bytearray(value_path.read_bytes())
            payload[-1] ^= 1
            value_path.write_bytes(payload)
        elif mutation == "shape":
            descriptor["value_shape"] = [999, 4]
        else:
            values = np.lib.format.open_memmap(value_path, mode="r+")
            values[0, 0] = np.nan + 0.0j
            values.flush()
            del values
            descriptor["value_file_sha256"] = hashlib.sha256(
                value_path.read_bytes()
            ).hexdigest()
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n",
            encoding="utf-8",
        )
        result = compare_canonical_matrices(base_manifest, manifest_path, prefixes=(1,))
        assert result["passed"] is False, mutation
        assert result["errors"], mutation


def test_canonical_matrix_writer_ast_is_streaming_and_metadata_only():
    path = Path(__file__).parents[2] / "benchmarks" / "canonical_matrix_artifacts.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    forbidden_calls = {"allgather", "column_stack", "vstack", "stack"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden_calls
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden_calls
    assert "open_memmap" in text
    assert "comm.gather" in text
    assert ".copy(" not in text
