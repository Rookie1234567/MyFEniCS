"""Thin J1 contract worker; it deliberately does not stage or run a JIT."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from benchmarks.task038_full3d_jit_staging import (
    EXPECTED_BRANCH,
    EXPECTED_INPUT_SHA256,
    EXPECTED_MODE_MANIFEST_SHA256,
    EXPECTED_PHYSICAL_MODEL_SHA256,
    MARKER_SCHEMA,
    SAMPLE_SCHEMA,
    append_jsonl,
    cache_manifest,
    create_fresh_cache,
    marker_manifest,
    prepare_fresh_root,
    process_tree_snapshot,
    sha256_file,
    write_marker,
)


RECORD_SCHEMA = "task038.v14.j1b.record.v1"
STAGE = "j1-contract"
PROFILE = {
    "wavelength_nm": 13.5,
    "grazing_angle_deg": 1.0,
    "theta_deg": 89.0,
    "phi_deg": 0.0,
    "polarization": "s",
    "p_degree": 6,
    "h_nm": 10,
    "mesh_cell_type": "hexahedron",
    "mesh_spacing_mode": "boundary_fitted",
}
FLAGS = {"compile": False, "mesh": False, "jit": False, "pde": False}


def _write_exclusive_json(path: Path, value: object) -> None:
    encoded = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _valid_source_sha(value: str) -> bool:
    return len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def _command_facts(source_sha: str, root: Path) -> dict:
    return {
        "argv": [str(value) for value in sys.argv],
        "executable": os.path.abspath(sys.executable),
        "cwd": os.path.abspath(os.getcwd()),
        "mode": "j1-contract",
        "artifact_root": str(root),
        "source_sha": source_sha,
    }


def run_contract(artifact_root: Path | str, source_sha: str) -> Path:
    if not _valid_source_sha(source_sha):
        raise ValueError("source-sha must be a lowercase 40-character SHA")
    root = Path(os.path.abspath(os.fspath(artifact_root)))
    cache_dir = root / "jit_cache"
    layout = prepare_fresh_root(root, cache_dir)
    marker_dir = layout["marker_dir"]
    record_path = root / "j1_record.json"
    sample_path = root / "process_samples.jsonl"
    cache_manifest_path = root / "cache_manifest.json"
    marker_manifest_path = root / "marker_manifest.json"
    common_facts = {
        "stage": STAGE,
        "artifact_root": str(root),
        "cache_dir": str(cache_dir),
        "source_sha": source_sha,
        "compile": False,
        "mesh": False,
        "jit": False,
        "pde": False,
    }
    write_marker(marker_dir, "parent_started", {**common_facts, "record_path": str(record_path)})
    create_fresh_cache(cache_dir)
    write_marker(marker_dir, "fresh_cache_created", common_facts)

    sample = process_tree_snapshot(os.getpid(), STAGE, exit_code=None)
    append_jsonl(sample_path, sample)
    cache_facts = cache_manifest(cache_dir)
    _write_exclusive_json(cache_manifest_path, cache_facts)

    write_marker(
        marker_dir,
        "parent_complete",
        {
            **common_facts,
            "record_path": str(record_path),
            "status": "contract_observed",
            "execution": "no_jit",
            "compiler_descendant_count": sample["compiler_descendant_count"],
        },
    )
    marker_facts = marker_manifest(marker_dir)
    _write_exclusive_json(marker_manifest_path, marker_facts)

    record = {
        "schema": RECORD_SCHEMA,
        "status": "contract_observed",
        "execution": "no_jit",
        "stage": STAGE,
        "source_sha": source_sha,
        "branch": EXPECTED_BRANCH,
        "identity": {
            "input_sha256": EXPECTED_INPUT_SHA256,
            "physical_model_sha256": EXPECTED_PHYSICAL_MODEL_SHA256,
            "mode_manifest_sha256": EXPECTED_MODE_MANIFEST_SHA256,
        },
        "profile": PROFILE,
        "flags": FLAGS,
        "command": _command_facts(source_sha, root),
        "paths": {
            "artifact_root": str(root),
            "cache_dir": str(cache_dir),
            "marker_dir": str(marker_dir),
            "record": str(record_path),
            "process_samples": str(sample_path),
            "cache_manifest": str(cache_manifest_path),
            "marker_manifest": str(marker_manifest_path),
        },
        "process": {
            "sample_count": 1,
            "sample_schema": SAMPLE_SCHEMA,
            "sample_path": str(sample_path),
            "sample_sha256": sha256_file(sample_path),
            "root_pid": sample["root_pid"],
            "all_status_readable": sample["all_status_readable"],
            "compiler_descendant_count": sample["compiler_descendant_count"],
        },
        "cache": {
            "manifest_path": str(cache_manifest_path),
            "manifest_sha256": sha256_file(cache_manifest_path),
            "artifact_count": cache_facts["artifact_count"],
        },
        "markers": {
            "manifest_path": str(marker_manifest_path),
            "manifest_sha256": sha256_file(marker_manifest_path),
            "names": [entry["name"] for entry in marker_facts],
        },
        "marker_schema": MARKER_SCHEMA,
    }
    _write_exclusive_json(record_path, record)
    return record_path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("j1-contract",), required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--source-sha", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        run_contract(args.artifact_root, args.source_sha)
    except (FileExistsError, FileNotFoundError, ValueError) as error:
        print(f"J1 contract refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
