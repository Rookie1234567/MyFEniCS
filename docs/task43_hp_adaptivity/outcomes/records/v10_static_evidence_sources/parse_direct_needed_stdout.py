#!/usr/bin/env python3
"""Derive a corrected edge map only from the preserved V9 text output."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


EXPECTED_STDOUT_SHA256 = "42700961db2b4ca1ae2206d93c18a6e0ad8986ec72b818b26a192b082eb005c4"
EXPECTED_SHELL_SHA256 = "1568de57c0911a88c062df5b9d504ae42fad3e0b93217f730e55f2631ee1b8b2"
STDOUT_REL = "benchmarks/artifacts/task43/v9_resume_preparation/raw/map_direct_needed_paths.stdout"
SHELL_REL = "benchmarks/artifacts/task43/v9_resume_preparation/raw/map_direct_needed_paths.sh"
V1_MAP_REL = "docs/task43_hp_adaptivity/outcomes/records/v9_d3_sources/preparation/direct_needed_edge_map.json"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def kv_header(line: str, prefix: str) -> dict[str, str]:
    body = line.removeprefix(prefix).strip()
    return dict(re.findall(r"([A-Za-z_]+)=([^\s]+)", body))


def parse_raw_lines(lines: list[str]) -> tuple[list[dict], list[dict]]:
    edges: list[dict] = []
    bridges: list[dict] = []
    current: dict | None = None
    current_kind: str | None = None

    def flush() -> None:
        nonlocal current, current_kind
        if current is None:
            return
        if current_kind == "edge":
            required = {
                "parent", "needed_soname", "resolution_source", "candidate_path",
                "realpath", "resolved_sha256", "build_id", "resolved_soname",
                "package_owner_line", "package",
            }
            missing = sorted(required - current.keys())
            if missing:
                raise ValueError(f"edge at line {current['source_line_start']} missing {missing}")
            edges.append(current)
        elif current_kind == "bridge":
            required = {
                "soname", "candidate_path", "realpath", "resolved_sha256", "build_id",
                "resolved_soname", "package_owner_line", "package",
            }
            missing = sorted(required - current.keys())
            if missing:
                raise ValueError(f"bridge at line {current['source_line_start']} missing {missing}")
            bridges.append(current)
        current = None
        current_kind = None

    for line_number, line in enumerate(lines, start=1):
        if line.startswith("EDGE "):
            flush()
            fields = kv_header(line, "EDGE ")
            current_kind = "edge"
            current = {
                "source_line_start": line_number,
                "parent": fields["parent"],
                "needed_soname": fields["needed"],
                "resolution_source": fields["source"],
                "candidate_path": fields["candidate"],
                "realpath": fields["realpath"],
                "needed_by_resolved_object": [],
            }
            continue
        if line.startswith("BRIDGE "):
            flush()
            fields = kv_header(line, "BRIDGE ")
            bridge_name = re.match(r"BRIDGE\s+(\S+)", line)
            if bridge_name is None:
                raise ValueError(f"malformed BRIDGE header at line {line_number}")
            current_kind = "bridge"
            current = {
                "source_line_start": line_number,
                "soname": bridge_name.group(1),
                "candidate_path": fields["candidate"],
                "realpath": fields["realpath"],
                "needed_by_resolved_object": [],
            }
            continue
        if current is None:
            continue

        sha_match = re.fullmatch(r"([0-9a-f]{64})\s+(\S+)", line)
        if sha_match:
            current["resolved_sha256"] = sha_match.group(1)
            if sha_match.group(2) != current["realpath"]:
                raise ValueError(f"hash path does not match current object at line {line_number}")
            continue
        build_match = re.search(r"Build ID:\s*([0-9a-f]+)\s*$", line)
        if build_match:
            current["build_id"] = build_match.group(1)
            continue
        needed_match = re.search(r"\(NEEDED\).*Shared library: \[([^]]+)\]", line)
        if needed_match:
            current["needed_by_resolved_object"].append(needed_match.group(1))
            continue
        soname_match = re.search(r"\(SONAME\).*Library soname: \[([^]]+)\]", line)
        if soname_match:
            current["resolved_soname"] = soname_match.group(1)
            continue
        if line.startswith("PACKAGE_OWNER "):
            current["package_owner_line"] = line
            continue
        if line.startswith("PACKAGE "):
            current["package"] = line.removeprefix("PACKAGE ")
            current["source_line_end"] = line_number

    flush()
    return edges, bridges


def legacy_entry_lines(text: str, parent: str, needed: str) -> tuple[int, int]:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == f'"parent": "{parent}",' and i + 1 < len(lines):
            if lines[i + 1].strip() == f'"needed_soname": "{needed}",':
                for j in range(i + 2, len(lines)):
                    if lines[j].strip().startswith('"package":'):
                        return i + 1, j + 1
    return 0, 0


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: parse_direct_needed_stdout.py REPO_ROOT OUTPUT_DIR", file=sys.stderr)
        return 2
    repo = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve()
    raw_path = repo / STDOUT_REL
    shell_path = repo / SHELL_REL
    v1_path = repo / V1_MAP_REL
    raw_bytes = raw_path.read_bytes()
    shell_bytes = shell_path.read_bytes()
    v1_bytes = v1_path.read_bytes()
    raw_sha = sha256(raw_bytes)
    shell_sha = sha256(shell_bytes)
    if raw_sha != EXPECTED_STDOUT_SHA256:
        raise ValueError(f"raw stdout SHA mismatch: {raw_sha}")
    if shell_sha != EXPECTED_SHELL_SHA256:
        raise ValueError(f"capture shell SHA mismatch: {shell_sha}")

    raw_text = raw_bytes.decode("utf-8")
    lines = raw_text.splitlines()
    edges, bridges = parse_raw_lines(lines)
    old = json.loads(v1_bytes)
    old_edges = old["edges"]

    keys = [(edge["parent"], edge["needed_soname"]) for edge in edges]
    if len(edges) != 61 or len(set(keys)) != 61:
        raise ValueError(f"expected 61 unique edge keys, got {len(edges)} / {len(set(keys))}")
    parent_set = {edge["parent"] for edge in edges}
    bridge_paths = {bridge["realpath"] for bridge in bridges}
    frozen_parents = parent_set - bridge_paths
    if len(parent_set) != 18 or len(frozen_parents) != 15 or len(bridges) != 3:
        raise ValueError("parent/bridge counts do not match the frozen 15+3 split")
    bridge_edges = [edge for edge in edges if edge["parent"] in bridge_paths]
    frozen_edges = [edge for edge in edges if edge["parent"] not in bridge_paths]
    if len(frozen_edges) != 48 or len(bridge_edges) != 13:
        raise ValueError(f"expected 48+13 edges, got {len(frozen_edges)}+{len(bridge_edges)}")
    if any(edge["needed_soname"] != edge["resolved_soname"] for edge in edges):
        raise ValueError("a needed SONAME does not match the resolved object's SONAME")

    # A resolved path/hash has one internally consistent identity across all edges.
    identity_fields = (
        "resolved_sha256", "build_id", "needed_by_resolved_object",
        "resolved_soname", "package_owner_line", "package",
    )
    by_realpath: dict[str, list[dict]] = defaultdict(list)
    for edge in edges:
        by_realpath[edge["realpath"]].append(edge)
    for realpath, group in by_realpath.items():
        for field in identity_fields:
            values = {json.dumps(item[field], sort_keys=True) for item in group}
            if len(values) != 1:
                raise ValueError(f"metadata conflict for {realpath}: {field}")
    for bridge in bridges:
        matches = [edge for edge in edges if edge["realpath"] == bridge["realpath"]]
        for field in identity_fields:
            if matches and any(edge[field] != bridge[field] for edge in matches):
                raise ValueError(f"bridge/edge metadata conflict: {bridge['realpath']} {field}")

    resolved_objects = {
        realpath: {
            field: group[0][field]
            for field in identity_fields
        }
        for realpath, group in sorted(by_realpath.items())
    }
    if len(resolved_objects) != len(by_realpath):
        raise ValueError("resolved object identity table is not one-to-one by realpath")

    # The old v1 map is read only and compared field-by-field; all new values above
    # were independently parsed from raw EDGE/BRIDGE blocks.
    old_by_key = {(x["parent"], x["needed_soname"]): x for x in old_edges}
    new_by_key = {(x["parent"], x["needed_soname"]): x for x in edges}
    if set(old_by_key) != set(new_by_key):
        raise ValueError("legacy and independently parsed key sets differ")
    common_fields = sorted((set(old_edges[0]) & set(edges[0])) - {"source_line_start", "source_line_end"})
    corrections = []
    for key, new in new_by_key.items():
        old_item = old_by_key[key]
        changed = {field: {"v1": old_item[field], "corrected": new[field]}
                   for field in common_fields if old_item[field] != new[field]}
        if changed:
            start, end = legacy_entry_lines(v1_bytes.decode("utf-8"), *key)
            record = {
                "key": {"parent": key[0], "needed_soname": key[1]},
                "v1_json_field_lines": [start, end],
                "raw_stdout_lines": [new["source_line_start"], new["source_line_end"]],
                "changed_fields": changed,
            }
            corrections.append(record)
    if len(corrections) != 3 or sum(len(x["changed_fields"]) for x in corrections) != 12:
        raise ValueError(f"expected three entries/twelve field corrections, got {len(corrections)} / {sum(len(x['changed_fields']) for x in corrections)}")
    expected_v1_spans = {
        ("/usr/lib/x86_64-linux-gnu/openmpi/lib/openmpi3/mca_btl_ofi.so", "ld-linux-x86-64.so.2"): [781, 795],
        ("/usr/lib/libpsm1/libpsm_infinipath.so.1.16", "libc.so.6"): [829, 844],
        ("/usr/lib/x86_64-linux-gnu/libmca_common_ofi.so.10.0.2", "libc.so.6"): [885, 904],
    }
    observed_spans = {
        (row["key"]["parent"], row["key"]["needed_soname"]): row["v1_json_field_lines"]
        for row in corrections
    }
    if observed_spans != expected_v1_spans:
        raise ValueError(f"legacy row spans differ from independently reviewed positions: {observed_spans}")

    corrected_map = {
        "schema": "task43.v10.s1_direct_needed_edge_map.corrected.v1",
        "source": {
            "path": STDOUT_REL,
            "sha256": raw_sha,
            "line_count": len(lines),
            "capture_shell_path": SHELL_REL,
            "capture_shell_sha256": shell_sha,
            "legacy_v1_map_path": V1_MAP_REL,
            "legacy_v1_map_sha256": sha256(v1_bytes),
            "legacy_parser_or_generator": "NOT_RECOVERABLE_FROM_PRESERVED_ARTIFACTS; the saved shell captures raw text and does not serialize the V1 JSON; exact prior tool invocation/source/time are unavailable.",
        },
        "scope": "stdlib text parsing of preserved output only; no activation, project import, readelf, ldd, ompi_info, library load, or environment scan",
        "counts": {
            "unique_edge_keys": len(keys),
            "parent_objects": len(parent_set),
            "frozen_15_edges": len(frozen_edges),
            "bridge_parent_edges": len(bridge_edges),
            "resolved_realpaths": len(by_realpath),
            "candidate_path_realpath_aliases": sum(
                edge["candidate_path"] != edge["realpath"] for edge in edges
            ),
            "unresolved": 0,
            "needed_soname_mismatches": 0,
        },
        "parent_objects": sorted(parent_set),
        "resolved_objects_by_realpath": resolved_objects,
        "edges": edges,
        "bridges": bridges,
        "candidate_realpath_aliases": [
            {
                "candidate_path": edge["candidate_path"],
                "realpath": edge["realpath"],
                "needed_soname": edge["needed_soname"],
                "resolved_soname": edge["resolved_soname"],
                "resolved_sha256": edge["resolved_sha256"],
            }
            for edge in edges
            if edge["candidate_path"] != edge["realpath"]
        ],
        "mpi_pmix_psm_edges": [
            edge for edge in edges
            if any(
                token in " ".join((edge["parent"], edge["needed_soname"], edge["realpath"], edge["package"])).lower()
                for token in ("mpi", "pmix", "psm")
            )
        ],
    }
    old_sha = sha256(v1_bytes)
    diff = {
        "schema": "task43.v10.s1_direct_needed_edge_field_diff.v1",
        "legacy_map_sha256": old_sha,
        "corrected_map_source_sha256": raw_sha,
        "unchanged_keys": 58,
        "corrected_keys": len(corrections),
        "corrected_fields_total": 12,
        "entries": corrections,
    }
    excerpt_ranges = [(415, 431), (447, 462), (485, 504)]
    excerpts = []
    for start, end in excerpt_ranges:
        selected = lines[start - 1:end]
        excerpts.append({
            "line_range": [start, end],
            "range_sha256_no_terminal_newline": sha256("\n".join(selected).encode()),
            "lines": [
                {"line": start + offset, "sha256_no_newline": sha256(line.encode()), "text": line}
                for offset, line in enumerate(selected)
            ],
        })
    boundary = {
        "schema": "task43.v10.s1_direct_needed_raw_boundaries.v1",
        "source_path": STDOUT_REL,
        "source_sha256": raw_sha,
        "excerpts": excerpts,
        "interpretation": [
            "415-420 is the loader EDGE block; the next block 423-431 starts an independent PSM BRIDGE record.",
            "447-453 is a libc EDGE block; 454-462 starts an independent common-ofi BRIDGE record.",
            "485-491 is a libc EDGE block; 492-504 starts an independent libfabric BRIDGE record.",
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        output_dir / "direct_needed_edge_map_corrected.json": corrected_map,
        output_dir / "direct_needed_edge_field_diff.json": diff,
        output_dir / "direct_needed_raw_boundary_excerpts.json": boundary,
    }
    for path, value in outputs.items():
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS_STATIC_DERIVATION",
        "raw_sha256": raw_sha,
        "capture_shell_sha256": shell_sha,
        "edges": len(edges),
        "parents": len(parent_set),
        "frozen_edges": len(frozen_edges),
        "bridge_edges": len(bridge_edges),
        "realpaths": len(by_realpath),
        "corrections": len(corrections),
        "changed_fields": sum(len(x["changed_fields"]) for x in corrections),
        "outputs": [str(path) for path in outputs],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
