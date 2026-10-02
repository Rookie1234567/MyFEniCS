"""Independent, saved-only checker for the reviewed fresh direct X/XZ/Y profiles.

Importing this module is standard-library only. Numerical dependencies are
loaded solely by the explicitly supervised checker entry point; the checker
does not assemble forms, instantiate a live carrier, factor, or solve.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

SCHEMA = "task40extra.y-orbit-direct-profile-probe.v1"
CHECKER_SCHEMA = "task40extra.y-orbit-direct-profile-checker.v1"
CARRIER_SCHEMA = "task40extra.direct-fresh-carrier-qualification.v1"
PASSES = {"prefactor": "QUOTIENT_PREFACTOR_COMPARE_PASS", "solve": "QUOTIENT_FULL3D_INVERSE_PROBE_PASS"}
SOURCES = ("generic", "interior_only", "physical", "notch_supported")
Q_ROWS = (2788, 2864, 2864, 2864)
Q_PORTS = (76, 152, 152, 152)
SECTOR_PORTS = (228, 304)
TREE_CAP_BYTES = 3 * 1024**3 // 2
RESERVE_BYTES = 128 * 1024**2
FACTOR_ALLOWANCE_BYTES = 512 * 1024**2
INPUT_SHA = "6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e"
PHYSICAL_MANIFEST = "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951"
PAIR_FIELDS = ("raw_component_0", "raw_component_1", "raw_C", "raw_D",
               "after_component_mask_C", "after_component_mask_D", "component_masked_entries_0",
               "component_masked_entries_1", "stored_C_sparse", "stored_D_sparse")


DIRECT_EVENT_WORKER_HEAD = "816b7247c8359a7affbd450365de5bbb86de367a"
DIRECT_EVENT_WORKER_SOURCE_SHA = "b17eac7ff5e937688ae8f7ed05a26327942637f326e6401027277f88f55030d2"
DIRECT_EVENT_WORKER_CHECKERS = {
    "benchmarks/check_y_orbit_direct_probe.py": "ef0bd44c7fcc1ba852fc00e8a74b7851d62cba4f231bbb773681585d98b61d55",
    "benchmarks/check_y_orbit_quotient_probe.py": "77b4090ebf4395b1e8f37b72def54fde05f4dc09ef466395898b5c2ef0f0c42a",
}
DIRECT_EVENT_ALLOWED_PATHS = frozenset((*DIRECT_EVENT_WORKER_CHECKERS,
    "src/test/test_y_orbit_direct_event_stream_metadata.py"))
DIRECT_EVENT_CHUNK_BYTES = 1 << 20
DIRECT_EVENT_MAX_LINE_BYTES = 64 << 20


def file_sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            result.update(block)
    return result.hexdigest()


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def canonical_digest(value):
    from src.solvers.fullspace_dtn_action import _canonical_json_bytes
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bind_direct_checker_source(worker_source, checker_source, *, direct_profile="X"):
    """Only the immutable816b X worker's two checkers and one test may differ."""
    require(direct_profile in ("X", "XZ", "Y"), "only explicit reviewed direct X/XZ/Y checker profiles are admitted")
    for source in (worker_source, checker_source):
        require(isinstance(source, dict) and source.get("dirty") == ""
            and isinstance(source.get("head"), str) and re.fullmatch(r"[0-9a-f]{40}", source["head"])
            and isinstance(source.get("branch"), str) and source["branch"]
            and isinstance(source.get("files_sha256"), dict) and source["files_sha256"]
            and all(isinstance(path, str) and isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha)
                for path, sha in source["files_sha256"].items()),
            "complete actual clean worker/checker source inventories required")
    require({key: value for key, value in worker_source.items() if key not in ("head", "files_sha256")}
        == {key: value for key, value in checker_source.items() if key not in ("head", "files_sha256")},
        "worker/checker source metadata outside the explicit HEAD/inventory bridge differs")
    old, new = worker_source["files_sha256"], checker_source["files_sha256"]
    changed = sorted(path for path in set(old) | set(new) if old.get(path) != new.get(path))
    same = worker_source == checker_source
    if worker_source["head"] == checker_source["head"]:
        require(same, "same-head direct checker requires exact complete source identity")
    else:
        require(direct_profile == "X" and worker_source["head"] == DIRECT_EVENT_WORKER_HEAD
            and digest_json(old) == DIRECT_EVENT_WORKER_SOURCE_SHA
            and all(old.get(path) == sha for path, sha in DIRECT_EVENT_WORKER_CHECKERS.items())
            and set(changed) == DIRECT_EVENT_ALLOWED_PATHS and set(old).issubset(new)
            and "src/test/test_y_orbit_direct_event_stream_metadata.py" not in old,
            "cross-head direct recheck permits only the pinned816b checker/event-loader/test correction")
    return {"schema": f"task40extra.direct-{direct_profile}-checker-event-stream-source-bridge.v1",
        "worker_head": worker_source["head"], "checker_head": checker_source["head"],
        "same_head_exact_source_identity": same, "allowed_checker_test_paths": sorted(DIRECT_EVENT_ALLOWED_PATHS),
        "changed_paths": changed, "all_other_numerical_config_input_dependencies_equal": True,
        "worker_dependency_manifest_sha256": digest_json(old), "checker_dependency_manifest_sha256": digest_json(new),
        "changed_dependencies": [{"path": path, "worker_sha256": old.get(path), "checker_sha256": new.get(path)}
            for path in changed]}



def validate_context_source_role(role, context, worker_source, *, source_root=None, direct_profile="X"):
    """Bind the exact ordinary/global or quotient/local source inventory."""
    metadata = reviewed_direct_profile_metadata(direct_profile)
    base = {
        "dtn_boundary_phase_gauge.py": "src/solvers/dtn_boundary_phase_gauge.py",
        "dtn_port_3d.py": "src/solvers/dtn_port_3d.py",
        "fullspace_dtn_action.py": "src/solvers/fullspace_dtn_action.py",
        "fullspace_same_mesh_hcurl_pmg_physical.py": "src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py",
        "dtn_boundary_plane_qualification.py": "src/solvers/dtn_boundary_plane_qualification.py",
        "modes_3d.py": "src/common/modes_3d.py",
        "config_3d.py": "src/common/config_3d.py",
    }
    extra = {
        "y_orbit_quotient_context.py": "src/solvers/y_orbit_quotient_context.py",
        "fullspace_same_mesh_hcurl_pmg_global.py": "src/solvers/fullspace_same_mesh_hcurl_pmg_global.py",
        "y_orbit_condensed_adapter.py": "src/solvers/y_orbit_condensed_adapter.py",
        "floquet_3d.py": "src/constraints/floquet_3d.py",
        "floquet_3d_high_order.py": "src/constraints/floquet_3d_high_order.py",
        "high_order_floquet_trace.py": "src/constraints/high_order_floquet_trace.py",
    }
    require(role in ("full", *(f"twist_{b}" for b in range(metadata.replication_count))),
            "unknown direct carrier context role")
    expected = dict(base)
    if role == "full":
        require("y_orbit_quotient" not in context, "full carrier cannot use a quotient context")
    else:
        expected.update(extra)
        quotient = context.get("y_orbit_quotient")
        require(isinstance(quotient, dict) and isinstance(quotient.get("contract"), dict),
                "local carrier requires its explicit quotient contract")
        contract = quotient["contract"]
        twist = int(role[-1])
        require(contract.get("schema") == "task40extra.y-orbit-two-cell-context.research.v1"
            and type(contract.get("twist_index")) is int and contract["twist_index"] == twist
            and contract.get("direct_profile") == metadata.name
            and quotient.get("contract_sha256") == digest_json(contract)
            and contract.get("physical_generator_manifest_sha256") == PHYSICAL_MANIFEST
            and contract.get("global_y_cells") == metadata.ny and contract.get("local_y_cells") == metadata.local_y_cells
            and contract.get("global_q_indices") == [twist, twist+metadata.replication_count]
            and contract.get("global_mode_count") == 532 and contract.get("sector_mode_count") == metadata.sector_port_counts[twist]
            and contract.get("replication_count") == metadata.replication_count
            and quotient.get("actual_local_cells") == metadata.local_cell_count
            and quotient.get("actual_local_storage_rows") == metadata.local_storage_rows
            and quotient.get("twist_requires_global_dual_rhs_transport") is True,
            "local carrier role differs from its hash-bound actual quotient contract")
    sources = context.get("source_sha256")
    require(isinstance(sources, dict) and set(sources) == set(expected),
            "exact role-specific carrier source inventory differs")
    root = Path(__file__).resolve().parents[1] if source_root is None else Path(source_root).resolve()
    inventory = worker_source.get("files_sha256")
    require(isinstance(inventory, dict), "complete immutable worker source inventory required")
    checked = {}
    for name, relative_path in expected.items():
        digest = sources[name]
        require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest),
                "carrier source hash must be an exact SHA256")
        path = root/relative_path
        require(path.is_file() and inventory.get(relative_path) == digest and file_sha(path) == digest,
                "actual carrier context source differs from immutable worker source: "+name)
        checked[name] = {"path": str(path), "sha256": digest}
    return checked


def load_direct_events(path, allocation_gate):
    """Retain every event in order, with bounded reads and admission before parse.

    First scan records only line byte lengths and the full file hash. The second
    pass admits each exact line's parse/list-growth scratch against current RSS.
    Key interning changes storage only; dictionaries and validator input remain
    identical to the old complete JSONL decode. Neither pass drops any event.
    """
    import sys
    path = Path(path)
    def identity():
        value = path.stat()
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    initial = identity()
    lengths, partial, total = [], 0, 0
    scanned = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            allocation_gate("direct_checker_event_scan_chunk", {"matrix_payload_bytes": 0,
                "workspace_bytes": 2*DIRECT_EVENT_CHUNK_BYTES + (4 << 20)})
            chunk = stream.read(DIRECT_EVENT_CHUNK_BYTES)
            if not chunk:
                break
            scanned.update(chunk); total += len(chunk)
            count = chunk.count(b"\n")
            allocation_gate("direct_checker_event_line_inventory", {"matrix_payload_bytes": 0,
                "workspace_bytes": 64*(count+1) + 16*(len(lengths)+count+1)
                    + 2*DIRECT_EVENT_CHUNK_BYTES + (4 << 20)})
            start = 0
            while True:
                stop = chunk.find(b"\n", start)
                if stop < 0:
                    partial += len(chunk)-start
                    require(partial <= DIRECT_EVENT_MAX_LINE_BYTES, "event JSONL line exceeds bounded maximum")
                    break
                length = partial + stop-start+1
                require(length <= DIRECT_EVENT_MAX_LINE_BYTES, "event JSONL line exceeds bounded maximum")
                lengths.append(length); partial = 0; start = stop+1
            del chunk
    require(partial == 0 and total == initial[2] and identity() == initial,
        "event JSONL must have complete newline-delimited EOF and stable file identity")
    events, parsed, blanks = [], hashlib.sha256(), 0
    with path.open("rb") as stream:
        for number, length in enumerate(lengths, 1):
            allocation_gate("direct_checker_event_json_line", {"matrix_payload_bytes": 0,
                "workspace_bytes": 8*length + 16*(len(events)+1) + (4 << 20), "event_line_number": number,
                "event_line_bytes": length, "retained_event_count": len(events)})
            line = stream.readline(length+1)
            require(len(line) == length and line.endswith(b"\n"), "event line changed between complete scan and parse")
            parsed.update(line)
            if not line.strip():
                blanks += 1
            else:
                value = json.loads(line, object_pairs_hook=lambda pairs: {sys.intern(key): item for key, item in pairs})
                require(isinstance(value, dict) and isinstance(value.get("event"), str) and value["event"],
                    "every retained event must be a JSON object with its actual event name")
                events.append(value)
            del line
        allocation_gate("direct_checker_event_full_EOF", {"matrix_payload_bytes": 0, "workspace_bytes": 1})
        require(stream.read(1) == b"", "event JSONL has unscanned trailing bytes")
    require(parsed.hexdigest() == scanned.hexdigest() and identity() == initial,
        "complete event file bytes/hash changed between scan and parse")
    return events, {"path": path.name, "file_sha256": parsed.hexdigest(), "file_bytes": int(total),
        "line_count": int(len(lengths)), "blank_line_count": int(blanks), "event_count": int(len(events)),
        "maximum_line_bytes": int(max(lengths, default=0)), "read_chunk_bytes": int(DIRECT_EVENT_CHUNK_BYTES),
        "maximum_admitted_line_bytes": int(DIRECT_EVENT_MAX_LINE_BYTES),
        "all_events_retained": True, "exact_event_order_preserved": True, "complete_EOF_verified": True,
        "same_file_hash_both_passes": True, "keys_interned_without_value_changes": True}


def finite_gate(value, limit, name):
    require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= limit,
            "finite nonnegative direct gate failed: " + name)
    return True


def validate_descriptor_metadata(reference, manifest):
    """Exact writer fields, with only the producer's payload-hash enrichment."""
    fields = {"path", "file_sha256", "shape", "dtype", "payload_bytes",
              "finite_entries", "nonfinite_entries", "raw_failure_diagnostic_only"}
    require(isinstance(reference, dict) and isinstance(manifest, dict)
        and set(manifest) == fields and fields.issubset(reference)
        and set(reference).issubset(fields | {"array_sha256"}),
        "descriptor may add only the known array_sha256 payload hash")
    for descriptor in (reference, manifest):
        shape = descriptor["shape"]
        require(isinstance(shape, list) and all(type(size) is int and size >= 0 for size in shape)
            and type(descriptor["payload_bytes"]) is int and descriptor["payload_bytes"] >= 0
            and type(descriptor["finite_entries"]) is int and descriptor["finite_entries"] == math.prod(shape)
            and type(descriptor["nonfinite_entries"]) is int and descriptor["nonfinite_entries"] == 0
            and descriptor["raw_failure_diagnostic_only"] is False
            and isinstance(descriptor["dtype"], str) and descriptor["dtype"]
            and isinstance(descriptor["path"], str) and descriptor["path"]
            and not Path(descriptor["path"]).is_absolute()
            and re.fullmatch(r"[0-9a-f]{64}", descriptor["file_sha256"]),
            "complete finite writer descriptor fields are required")
    require(json.dumps({key: reference[key] for key in fields}, sort_keys=True, allow_nan=False)
        == json.dumps(manifest, sort_keys=True, allow_nan=False),
        "every shared descriptor field must match the exact current manifest")
    if "array_sha256" in reference:
        require(isinstance(reference["array_sha256"], str)
            and re.fullmatch(r"[0-9a-f]{64}", reference["array_sha256"]),
            "literal lowercase SHA256 is required for descriptor enrichment")
    return True


def validate_descriptor_payload(reference, manifest, value):
    """Recompute enriched C-order payload hashes in bounded readonly panels."""
    validate_descriptor_metadata(reference, manifest)
    require(not value.dtype.hasobject and value.flags.writeable is False
        and list(value.shape) == manifest["shape"] and str(value.dtype) == manifest["dtype"]
        and value.nbytes == manifest["payload_bytes"] and value.size == math.prod(manifest["shape"]),
        "descriptor enrichment requires the exact readonly manifest-bound array")
    if "array_sha256" in reference:
        digest = hashlib.sha256()
        entries = max(1, (1 << 20) // int(value.dtype.itemsize))
        # ndarray.flat traverses logical C order even for a Fortran-order mmap.
        for start in range(0, value.size, entries):
            panel = value.flat[start:start+entries]
            digest.update(panel.tobytes(order="C"))
            del panel
        require(digest.hexdigest() == reference["array_sha256"],
                "enriched descriptor payload SHA256 differs from the saved readonly array")
    return True


def bound_path(root, relative):
    require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), "relative owned artifact path required")
    path = (Path(root).resolve() / relative).resolve()
    require(path.is_relative_to(Path(root).resolve()) and path.is_file(), "artifact escaped its own run directory")
    return path


def reviewed_direct_profile_metadata(name):
    """Only the three reviewed finite profiles may supply shape/count invariants."""
    require(name in ("X", "XZ", "Y"), "only explicit reviewed direct X/XZ/Y saved profiles are admitted")
    from src.solvers.y_orbit_direct_profile import direct_profile_metadata
    metadata = direct_profile_metadata(name)
    if name == "Y":
        require(metadata.dimensions == (4, 6, 5) and metadata.local_y_cells == 2
            and metadata.replication_count == 3 and metadata.q_port_counts == (76, 76, 76, 152, 76, 76)
            and metadata.sector_port_counts == (228, 152, 152)
            and metadata.augmented_rows_per_q == (1884, 1884, 1884, 1960, 1884, 1884)
            and (metadata.cell_count, metadata.storage_rows, metadata.independent_rows, metadata.interior_rows, metadata.trace_rows)
                == (120, 25468, 23808, 12960, 10848)
            and (metadata.local_cell_count, metadata.local_storage_rows, metadata.local_independent_rows,
                metadata.local_interior_rows, metadata.local_trace_rows, metadata.rows_per_q, metadata.trace_rows_per_q)
                == (40, 8940, 7936, 4320, 3616, 3968, 1808)
            and metadata.factor_allowance_per_q_bytes == 128*1024**2
            and metadata.factor_allowance_aggregate_bytes == 768*1024**2
            and metadata.evidence_reserve_bytes == RESERVE_BYTES,
            "Y requires the exact reviewed six-q/three-twist mesh/channel/resource inventory")
    return metadata


def validate_profile(profile):
    require(isinstance(profile, dict), "complete reviewed direct profile metadata required")
    metadata = reviewed_direct_profile_metadata(profile.get("name"))
    fields = ("name", "dimensions", "global_axes", "local_axes", "replication_count", "local_y_cells",
        "cell_count", "storage_rows", "independent_rows", "interior_rows", "trace_rows", "rows_per_q",
        "trace_rows_per_q", "local_cell_count", "local_storage_rows", "local_independent_rows",
        "local_interior_rows", "local_trace_rows", "q_port_counts", "sector_port_counts",
        "augmented_rows_per_q", "physical_mode_count", "complete_cell_dimension", "complete_cell_interior_dimension",
        "factor_allowance_per_q_bytes", "factor_allowance_aggregate_bytes", "evidence_reserve_bytes")
    identity = json.loads(json.dumps(metadata.identity()))
    require(all(profile.get(key) == identity[key] for key in fields),
            "complete unchanged reviewed mesh/channel/alias/resource profile required")
    return True


def validate_direct_mode_roles(physical_modes, direct_profile):
    """Count every original physical alias against the reviewed q/sector roles."""
    metadata = reviewed_direct_profile_metadata(direct_profile)
    keys = [(mode.side, int(mode.m), int(mode.n), mode.polarization) for mode in physical_modes]
    require(len(keys) == len(set(keys)) == 532
        and tuple(sum(int(mode.n) % metadata.ny == q for mode in physical_modes)
            for q in range(metadata.ny)) == metadata.q_port_counts,
        "all532 unique original physical aliases and exact reviewed q counts required")
    sectors = [[i for i, mode in enumerate(physical_modes)
        if (int(mode.n)-b) % metadata.replication_count == 0]
        for b in range(metadata.replication_count)]
    require(tuple(map(len, sectors)) == metadata.sector_port_counts
        and sorted(index for sector in sectors for index in sector) == list(range(532)),
        "every original physical alias must occur exactly once across reviewed twists")
    return sectors


def validate_direct_Y_operator_coverage(proof):
    """Bind the public recomputation's complete six-q/three-twist coverage."""
    metadata = reviewed_direct_profile_metadata("Y")
    sources = proof.get("sources", [])
    require(len(sources) == 4, "Y requires one full and all three local source proofs")
    for index, source in enumerate(sources):
        require(source.get("cell_count") == (metadata.cell_count if index == 0 else metadata.local_cell_count)
            and source.get("independent_rows") == (metadata.independent_rows if index == 0 else metadata.local_independent_rows)
            and source.get("all_interior_rows") == (metadata.interior_rows if index == 0 else metadata.local_interior_rows)
            and source.get("full300_columns_per_cell") == 300 and source.get("complete_actual_coverage") is True,
            "Y public source proof must cover every original cell/channel/column")
    orbits = proof.get("complete_actual_xz_y_orbits", [])
    require(len(orbits) == 20
        and [tuple(item.get("grid_xz", [])) for item in orbits]
            == [(ix, iz) for ix in range(metadata.nx) for iz in range(metadata.nz)],
        "Y requires all20 actual x-z orbits in their complete order")
    for orbit in orbits:
        pairs = orbit.get("all_global_q_pairs", [])
        require([(item.get("p"), item.get("q")) for item in pairs]
            == [(p, q) for p in range(6) for q in range(6)]
            and all(item.get("cross_twist") is (item["p"] % 3 != item["q"] % 3) for item in pairs)
            and sum(item["cross_twist"] for item in pairs) == 24,
            "each Y orbit requires all36 global and all24 cross-twist pairs")
        locals_ = orbit.get("local_twists", [])
        require([item.get("b") for item in locals_] == [0, 1, 2],
            "each Y orbit requires every actual local twist")
        for b, local in enumerate(locals_):
            require([(item.get("p"), item.get("q"), item.get("global_p"), item.get("global_q"))
                for item in local.get("all2x2_pairs", [])]
                == [(p, q, b+3*p, b+3*q) for p in range(2) for q in range(2)],
                "each Y orbit requires all12 local pairs with exact b/b+3 aliases")
    require(len(proof.get("local_original_condensation", [])) == 3
        and len(proof.get("existing_provider_all2x2_full_columns", [])) == 3,
        "Y requires complete original condensation and provider proofs for all three twists")
    return True


def validate_scope(report, stage):
    validate_profile(report.get("profile"))
    metadata = reviewed_direct_profile_metadata(report.get("direct_profile"))
    require(report["profile"]["name"] == metadata.name, "report profile and metadata identity differ")
    require(stage in PASSES and report.get("schema") == SCHEMA and report.get("stage") == stage
        and report.get("status") == PASSES[stage] and report.get("direct_profile") == metadata.name
        and report.get("degree") == 4 and report.get("physical_mode_count") == 532
        and report.get("source_clean_unchanged") is True and report.get("official_results") is False
        and report.get("prefactor_only") is (stage == "prefactor")
        and report.get("PDE_solved") is (stage == "solve")
        and report.get("factor_count") == (0 if stage == "prefactor" else metadata.ny)
        and report.get("input_sha256") == INPUT_SHA
        and report.get("physical_generator_manifest_sha256") == PHYSICAL_MANIFEST,
        "fresh reviewed direct stage/source/config identity differs")
    flags = report.get("scope_flags", {})
    require(all(flags.get(key) is True for key in ("full_layout_entity_stream", "fresh_global_and_local_carriers"))
        and all(flags.get(key) is False for key in ("snapshots_reused", "candidate_full_Ny_CSR_created",
            "candidate_full_F_created", "candidate_full_Q_created", "candidate_global_FE_square_matrix_created",
            "performance_or_target_capacity_claim")), "direct fresh/no-global-square scope required")
    require(report.get("shared_transforms") is True, "mandatory qualified shared representation required")
    if stage == "prefactor":
        require(not any(report.get(key) for key in ("factor", "augmented_controls", "regular_sources", "notched_sources")),
                "prefactor cannot carry factors or solved controls")
    else:
        require(all(set(report.get(key, {})) == set(SOURCES) for key in
                    ("regular_sources", "notched_sources", "sampled_right_PC_defect")), "all four full original load families required")
        require(report.get("PC_defect_is_norm_bound") is False and report.get("target_geometry_accuracy") is False
                and report.get("no_2TB_or_48h_claim") is True, "diagnostic/capacity scope differs")
        changed = report.get("changed_cells")
        require(isinstance(changed, list) and len(changed) == (3 if metadata.name == "Y" else 2)
                and len(set(changed)) == len(changed)
                and all(type(v) is int and 0 <= v < metadata.cell_count for v in changed), "actual exact reviewed changed-cell support required")
        for name in SOURCES:
            finite_gate(report["sampled_right_PC_defect"][name], float("inf"), "PC_" + name)
        coupling = report.get("sampled_notch_off_q_delta_relative")
        finite_gate(coupling, float("inf"), "notch_q_coupling")
        require(coupling >= 1e-8, "genuine full3D notch q coupling required")
    return True


def direct_memory_cap(direct_profile, stage, research_wall_seconds, research_memory_gib=None):
    """Select only the approved X/1800/2GiB and XZ/Y/4500/3GiB solve pairs."""
    if direct_profile == "Y":
        require(stage == "solve" and type(research_wall_seconds) is int and research_wall_seconds == 4500
            and type(research_memory_gib) is int and research_memory_gib == 3,
            "Y requires the explicit reviewed solve/wall4500/3GiB budget")
    if research_memory_gib is None:
        require(not (direct_profile in ("XZ", "Y") and research_wall_seconds == 4500),
                "XZ/Y wall4500 requires the explicit approved 3GiB memory request")
        return TREE_CAP_BYTES
    require(type(research_memory_gib) is int and type(research_wall_seconds) is int
        and stage == "solve"
        and (direct_profile, research_wall_seconds, research_memory_gib) in (("X", 1800, 2), ("XZ", 4500, 3), ("Y", 4500, 3)),
        "research memory requires literal X/solve/wall1800/2GiB or XZ/Y/solve/wall4500/3GiB")
    return research_memory_gib * 1024**3


def validate_direct_memory_launch(envelope, *, research_memory_gib=2, dynamic_cap_key="launch_cap_bytes",
                                  direct_profile=None, research_wall_seconds=None):
    """Check the saved launch's available host and every finite cgroup budget."""
    require(type(research_memory_gib) is int and research_memory_gib in (2, 3) and isinstance(envelope, dict),
            "literal approved memory launch metadata required")
    if direct_profile is None and research_wall_seconds is None:
        require(type(research_memory_gib) is int and research_memory_gib == 2,
                "historical launch helper default admits only literal 2GiB")
        selected_cap = 2 * 1024**3
    else:
        selected_cap = direct_memory_cap(direct_profile, "solve", research_wall_seconds, research_memory_gib)
    required = selected_cap + RESERVE_BYTES
    require(all(type(envelope.get(key)) is int and envelope[key] >= required
        for key in (dynamic_cap_key, "effective_available_bytes", "effective_total_bytes"))
        and type(envelope.get("reserve_bytes")) is int and envelope["reserve_bytes"] >= 0
        and envelope["effective_available_bytes"] <= envelope["effective_total_bytes"],
        "fresh dynamic launch must support the selected cap plus the evidence reserve")
    if research_memory_gib == 3:
        require(envelope["reserve_bytes"] >= 4 * 1024**3
            and envelope[dynamic_cap_key] <= max(0, envelope["effective_available_bytes"] - envelope["reserve_bytes"]),
            "XZ/Y launch requires the actual 4GiB host reserve before the 3GiB plus evidence-reserve admission")
    groups = envelope.get("cgroup_limits")
    require(isinstance(groups, list) and all(isinstance(group, dict)
        and type(group.get("limit_bytes")) is int and type(group.get("current_bytes")) is int
        and group["current_bytes"] >= 0 and group["limit_bytes"] - group["current_bytes"] >= required
        for group in groups), "every finite cgroup launch headroom must support cap plus evidence reserve")
    return True


def validate_direct_memory_admission(admission, *, direct_profile=None, research_wall_seconds=None):
    memory = admission.get("requested_memory_gib") if isinstance(admission, dict) else None
    if direct_profile is None and research_wall_seconds is None:
        require(type(memory) is int and memory == 2, "historical admission helper default admits only literal 2GiB")
        selected_cap = 2 * 1024**3
    else:
        selected_cap = direct_memory_cap(direct_profile, "solve", research_wall_seconds, memory)
    require(isinstance(admission, dict) and set(admission) == {"requested_memory_gib", "requested_tree_cap_bytes",
        "required_cap_plus_evidence_reserve_bytes", "fresh_memory_envelope", "launch_admission_passed"}
        and type(admission.get("requested_memory_gib")) is int and admission["requested_memory_gib"] == memory
        and type(admission.get("requested_tree_cap_bytes")) is int and admission["requested_tree_cap_bytes"] == selected_cap
        and type(admission.get("required_cap_plus_evidence_reserve_bytes")) is int
        and admission["required_cap_plus_evidence_reserve_bytes"] == selected_cap + RESERVE_BYTES
        and admission.get("launch_admission_passed") is True,
        "exact explicit research memory launch admission is required")
    validate_direct_memory_launch(admission["fresh_memory_envelope"], research_memory_gib=memory,
        direct_profile=direct_profile, research_wall_seconds=research_wall_seconds)
    return True


def validate_direct_supervision(summary, source, *, maximum_wall=600, direct_profile="X", stage="solve",
                                research_wall_seconds=None, research_memory_gib=None):
    if research_memory_gib is None:
        from benchmarks.y_orbit_two_cell_authority import validate_supervision
        return validate_supervision(summary, source, maximum_wall=maximum_wall)
    selected_cap = direct_memory_cap(direct_profile, stage, research_wall_seconds, research_memory_gib)
    launch = summary.get("launch_envelope", {})
    delta = summary.get("global_swap_activity", {}).get("delta", {})
    if (summary.get("classification") != "COMPLETED" or summary.get("leader_exit_code") != 0
            or summary.get("source_state") != source
            or summary.get("sampled_process_tree_swap_peak_bytes") != 0
            or summary.get("descendants_cleared") is not True
            or summary.get("process_tree_all_status_readable") is not True
            or summary.get("process_tree_all_identity_complete") is not True
            or not 0 < summary.get("sampled_process_tree_rss_peak_bytes", 0) < selected_cap
            or not 0 < summary.get("elapsed_seconds", 0) < maximum_wall
            or not 0 < launch.get("launch_cap_bytes", 0) <= selected_cap
            or delta.get("pswpin_pages") != 0 or delta.get("pswpout_pages") != 0):
        raise ValueError("supervised source/whole-tree/zero-global-swap/time identity failed")
    require(type(summary.get("sampled_process_tree_rss_peak_bytes")) is int
        and type(summary.get("elapsed_seconds")) in (int, float) and math.isfinite(summary["elapsed_seconds"])
        and type(launch.get("launch_cap_bytes")) is int and launch["launch_cap_bytes"] == selected_cap
        and type(launch.get("tree_cap_bytes")) is int and launch["tree_cap_bytes"] == selected_cap
        and launch.get("cap_policy") == "min(dynamic_memory_envelope, explicit_tree_cap)",
        "literal whole-tree/time and explicit selected launch identity failed")
    validate_direct_memory_launch(launch, dynamic_cap_key="dynamic_launch_cap_bytes", research_memory_gib=research_memory_gib,
        direct_profile=direct_profile, research_wall_seconds=research_wall_seconds)
    return True


def validate_metadata_bindings(report, provenance, manifest, *, checker_source, checker_environment, stage,
                               research_wall_seconds=None, research_memory_gib=None):
    validate_scope(report, stage)
    bind_direct_checker_source(report.get("source"), checker_source, direct_profile=report["direct_profile"])
    require(report.get("source") == provenance.get("source")
        and report.get("environment") == checker_environment == provenance.get("environment")
        and checker_source.get("dirty") == "" and re.fullmatch(r"[0-9a-f]{40}", checker_source.get("head", ""))
        and checker_source.get("files_sha256") and all(re.fullmatch(r"[0-9a-f]{64}", v)
            for v in checker_source["files_sha256"].values())
        and provenance.get("schema") == SCHEMA and provenance.get("stage") == stage
        and provenance.get("direct_profile") == report["direct_profile"] and provenance.get("degree") == 4
        and provenance.get("input_sha256") == INPUT_SHA and report.get("artifacts") == manifest and manifest,
        "exact immutable worker source/provenance/ABI/manifest and reviewed checker bridge required")
    if research_wall_seconds is not None:
        require(type(research_wall_seconds) is int
            and (report["direct_profile"], research_wall_seconds) in (("X", 1800), ("XZ", 4500), ("Y", 4500)),
            "only the explicit X/wall1800 or XZ/Y/wall4500 research request is admitted")
    wall_seconds = 600 if research_wall_seconds is None else research_wall_seconds
    selected_cap = direct_memory_cap(report.get("direct_profile"), stage, research_wall_seconds, research_memory_gib)
    metadata = reviewed_direct_profile_metadata(report["direct_profile"])
    expected = {"stage": stage, "wall_seconds": wall_seconds, "swap_bytes": 0, "mpi": 1, "math_threads": 1,
        "evidence_reserve_bytes": RESERVE_BYTES, "factor_workspace_allowance_bytes": 0 if stage == "prefactor" else metadata.factor_allowance_aggregate_bytes,
        "factor_fill_and_temporary_workspace_unknown": True, "factor_L_U_statistics_copies_permitted": False,
        "performance_or_target_capacity_claim": False}
    contract = provenance.get("resource_contract", {})
    require(all(contract.get(key) == value for key, value in expected.items())
        and type(contract.get("tree_cap_bytes")) is int and 0 < contract["tree_cap_bytes"] <= selected_cap
        and checker_environment.get("petsc_scalar_type") == "complex128", "whole-tree/explicit-time/zeroSwap/MPI1/thread1/ABI policy differs")
    command = provenance.get("command", [])
    require(command.count("--direct-profile") == 1 and command[command.index("--direct-profile") + 1:]
        and command[command.index("--direct-profile") + 1] == report["direct_profile"], "explicit reviewed profile command required")
    if research_wall_seconds is None:
        require("--research-wall-seconds" not in command and "research_wall_seconds" not in contract
            and "worker_phase_wall_seconds" not in contract, "ordinary600 contract cannot inherit a research override")
    else:
        phase = contract.get("worker_phase_wall_seconds")
        require(command.count("--research-wall-seconds") == 1
            and command[command.index("--research-wall-seconds") + 1:] and command[command.index("--research-wall-seconds") + 1] == str(research_wall_seconds)
            and contract.get("research_wall_seconds") == research_wall_seconds
            and type(phase) in (int, float) and math.isfinite(phase) and 0 < phase <= wall_seconds,
            "explicit worker argv/resource/remaining-phase timing differs")
    if research_memory_gib is None:
        require("--research-memory-gib" not in command and all(key not in contract for key in
            ("research_memory_gib", "requested_tree_cap_bytes", "research_memory_launch_admission")),
                "ordinary memory contract cannot inherit a research override")
    else:
        require(command.count("--research-memory-gib") == 1
            and command[command.index("--research-memory-gib") + 1:]
            and command[command.index("--research-memory-gib") + 1] == str(research_memory_gib)
            and type(contract.get("research_memory_gib")) is int and contract["research_memory_gib"] == research_memory_gib
            and type(contract.get("requested_tree_cap_bytes")) is int and contract["requested_tree_cap_bytes"] == selected_cap
            and contract["tree_cap_bytes"] == selected_cap,
            "explicit worker argv/resource memory cap differs")
        validate_direct_memory_admission(contract.get("research_memory_launch_admission"),
            direct_profile=report["direct_profile"], research_wall_seconds=research_wall_seconds)
    return True


def validate_research_timing(provenance, supervision, events, phase, *, research_wall_seconds=None, direct_profile="X"):
    """Join opt-in allocation/phase clocks to the actual worker watchdog cap."""
    if research_wall_seconds is None:
        return True
    require(type(research_wall_seconds) is int
        and (direct_profile, research_wall_seconds) in (("X", 1800), ("XZ", 4500), ("Y", 4500)),
        "research timing requires the exact explicit profile/wall request")
    seconds = provenance["resource_contract"]["worker_phase_wall_seconds"]
    require(supervision.get("time_reference_seconds", {}).get("workflow") == seconds
        and phase.get("research_wall_seconds") == research_wall_seconds
        and phase.get("phase_wall_seconds") == seconds
        and type(phase.get("worker_elapsed_seconds")) in (int, float)
        and math.isfinite(phase["worker_elapsed_seconds"]) and 0 <= phase["worker_elapsed_seconds"] < seconds,
        "worker phase and actual watchdog timing differ")
    allocations = [event for event in events if event.get("event") == "allocation_admission"]
    require(allocations and all(event.get("research_wall_seconds") == research_wall_seconds
        and event.get("phase_wall_seconds") == seconds
        and type(event.get("worker_elapsed_seconds")) in (int, float)
        and math.isfinite(event["worker_elapsed_seconds"]) and 0 <= event["worker_elapsed_seconds"] < seconds
        for event in allocations), "every actual allocation must bind the requested and remaining phase budgets")
    return True


def validate_research_memory_resources(provenance, supervision, events, phase, *, direct_profile="X", stage,
                                       research_wall_seconds=None, research_memory_gib=None):
    """Recompute every actual allocation cap and join the worker phase receipt."""
    selected_cap = direct_memory_cap(direct_profile, stage, research_wall_seconds, research_memory_gib)
    allocations = [event for event in events if event.get("event") == "allocation_admission"]
    if research_memory_gib is None:
        require(all(all(key not in packet for key in ("research_memory_gib", "requested_tree_cap_bytes"))
            for packet in [phase, *allocations]), "default packets cannot inherit a research memory override")
        return True
    contract = provenance["resource_contract"]
    validate_direct_memory_admission(contract.get("research_memory_launch_admission"),
        direct_profile=direct_profile, research_wall_seconds=research_wall_seconds)
    require(contract.get("tree_cap_bytes") == supervision.get("launch_envelope", {}).get("launch_cap_bytes") == selected_cap
        and type(phase.get("research_memory_gib")) is int and phase["research_memory_gib"] == research_memory_gib
        and type(phase.get("requested_tree_cap_bytes")) is int and phase["requested_tree_cap_bytes"] == selected_cap
        and allocations, "actual worker phase/resource/supervised launch cap differs")
    for event in allocations:
        require(type(event.get("research_memory_gib")) is int and event["research_memory_gib"] == research_memory_gib
            and type(event.get("requested_tree_cap_bytes")) is int and event["requested_tree_cap_bytes"] == selected_cap
            and type(event.get("launch_cap_bytes")) is int and event["launch_cap_bytes"] == selected_cap,
            "every actual allocation requires exact selected memory and launch identity")
        values = [event.get(key) for key in ("current_tree_rss_bytes", "additional_payload_bytes",
            "declared_workspace_bytes", "remaining_factor_allowance_bytes", "evidence_reserve_bytes")]
        envelope = event.get("fresh_memory_envelope", {})
        require(all(type(value) is int and value >= 0 for value in values) and values[0] > 0
            and values[-1] >= RESERVE_BYTES and event.get("projected_tree_bytes") == sum(values)
            and type(envelope.get("effective_available_bytes")) is int and envelope["effective_available_bytes"] >= 0
            and type(envelope.get("reserve_bytes")) is int and envelope["reserve_bytes"] >= 0
            and type(event.get("effective_tree_cap_bytes")) is int
            and event["effective_tree_cap_bytes"] == min(selected_cap, values[0]
                + envelope["effective_available_bytes"] - envelope["reserve_bytes"])
            and event["projected_tree_bytes"] < event["effective_tree_cap_bytes"] <= selected_cap
            and event.get("admitted") is True,
            "every actual current-RSS/payload/workspace/allowance/reserve projection must fit the recomputed cap")
    return True


def expected_array_shapes(report, stage):
    validate_profile(report.get("profile"))
    metadata = reviewed_direct_profile_metadata(report.get("direct_profile"))
    require(report["profile"]["name"] == metadata.name, "array report profile and metadata identity differ")
    q_rows, sector_ports = metadata.augmented_rows_per_q, metadata.sector_port_counts
    blocks = report.get("reformed_blocks", [])
    require(len(blocks) == metadata.ny and [b.get("q") for b in blocks] == list(range(metadata.ny)), "complete actual q input inventory required")
    expected = {}
    for q, block in enumerate(blocks):
        nnz = block.get("nnz")
        require(block.get("shape") == [q_rows[q], q_rows[q]] and block.get("csr_prefix") == f"q_{q}_S"
            and type(nnz) is int and 0 < nnz <= q_rows[q]**2
            and re.fullmatch(r"[0-9a-f]{64}", block.get("CSR_sha256", "")), "reviewed q CSR dimensions/hash/entries required")
        expected.update({f"q_{q}_S_data": [nnz], f"q_{q}_S_indices": [nnz], f"q_{q}_S_indptr": [q_rows[q] + 1]})
    providers = report.get("direct_provider_blocks", [])
    require(len(providers) == 4*metadata.replication_count and [(b.get("twist"), b.get("p"), b.get("q")) for b in providers]
        == [(b, p, q) for b in range(metadata.replication_count) for p in range(2) for q in range(2)], "all original local 2x2 blocks required")
    for block in providers:
        b, p, q = block["twist"], block["p"], block["q"]
        gp, gq = b + metadata.replication_count*p, b + metadata.replication_count*q
        nnz, prefix = block.get("nnz"), f"direct_twist_{b}_block_{p}_{q}"
        require(block.get("global_p") == gp and block.get("global_q") == gq
            and block.get("shape") == [q_rows[gp], q_rows[gq]] and block.get("csr_prefix") == prefix
            and type(nnz) is int and 0 <= nnz <= q_rows[gp]*q_rows[gq]
            and re.fullmatch(r"[0-9a-f]{64}", block.get("CSR_sha256", "")), "complete provider branch/alias/CSR identity differs")
        expected.update({prefix + "_data": [nnz], prefix + "_indices": [nnz], prefix + "_indptr": [q_rows[gp] + 1]})
    expected.update({"independent_storage_rows": [metadata.independent_rows], "actual_interior_positions": [metadata.interior_rows],
        "full_mpc_slaves": [metadata.storage_rows - metadata.independent_rows], "full_mpc_offsets": [metadata.storage_rows + 1], "port_original_H": [532],
        "port_q_labels": [532], "port_factor_coordinate_scale": [532], "original_mode_e_vectors": [532, 3],
        "original_mode_k_vectors": [532, 3], "original_mode_outward_signs": [532],
        "original_mode_magnetic_denominator": [], "original_mode_boundary_area": [],
        "original_mode_incident_projections": [532], "original_carrier_global_rows": [],
        "original_carrier_ownership_range": [2], "original_carrier_slave_rows": [metadata.storage_rows - metadata.independent_rows],
        "original_port_C_indptr": [533], "original_port_D_indptr": [533]})
    for b, ports in enumerate(sector_ports):
        expected.update({f"twist_{b}_{name}": [size] for name, size in
            (("independent_storage_rows", metadata.local_independent_rows), ("trace_original_rows", metadata.local_trace_rows), ("interior_original_rows", metadata.local_interior_rows),
             ("slave_storage_rows", metadata.local_storage_rows - metadata.local_independent_rows), ("original_H", ports))})
        if metadata.name == "Y":
            expected[f"direct_twist_{b}_lower_rhs_local_state"] = [metadata.local_independent_rows]
            expected[f"direct_twist_{b}_lower_rhs_global_state"] = [metadata.independent_rows]
    if stage == "solve":
        factor = report.get("factor", {})
        require([b.get("q") for b in factor.get("input_blocks", [])] == list(range(metadata.ny))
            and [b.get("q") for b in factor.get("tests", [])] == list(range(metadata.ny))
            and factor.get("all_reformed_blocks_compared_before_factor") is True
            and (factor.get("all_four_retained_simultaneously") is True if metadata.name != "Y" else
                factor.get("all_six_retained_simultaneously") is True
                and factor.get("all_actual_q_retained_simultaneously") is True
                and factor.get("all_four_retained_simultaneously") is False
                and factor.get("factor_allowance_aggregate_bytes") == metadata.factor_allowance_aggregate_bytes),
            "all actual simultaneous factors and tests required")
        for q, block in enumerate(factor["input_blocks"]):
            require(block.get("shape") == blocks[q]["shape"] and block.get("CSR_sha256") == blocks[q]["CSR_sha256"],
                    "factor detached from fresh original-proven input block")
            for name in ("rhs_a", "rhs_b", "solution_a", "solution_b", "solution_a_repeat", "solution_sum"):
                expected[f"q_{q}_{name}"] = [q_rows[q]]
        for q in range(metadata.ny):
            label = f"aug_q_{q}"
            expected.update({label + "_" + key: [metadata.independent_rows] for key in ("FE_rhs", "effective_rhs", "solution")})
            expected.update({label + "_" + key: [532] for key in
                ("port_rhs", "port_operation_scale", "auxiliary_ports", "projection", "normalization_h", "augmented_port_residual")})
            expected.update({label + "_" + key: [metadata.storage_rows] for key in
                ("rhs_storage", "solution_storage", "original_action", "volume_action", "coupling_action", "native_residual", "augmented_FE_residual")})
        for name in SOURCES:
            expected[name + "_rhs"] = [metadata.independent_rows]
            for family in ("regular", "notch"):
                label = family + "_" + name
                expected[label + "_solution"] = [metadata.independent_rows]
                expected.update({label + "_" + key: [metadata.storage_rows] for key in
                    ("rhs_storage", "solution_storage", "original_action", "volume_action", "coupling_action", "native_residual", "augmented_FE_residual", "recovered_field")})
                expected.update({label + "_" + key: [532] for key in
                    ("auxiliary_ports", "projection", "normalization_h", "augmented_port_residual", "plane_total_auxiliary",
                     "plane_incident_projections", "plane_outgoing_auxiliary", "direct_plane_outgoing_power_diagnostic",
                     "global_total_auxiliary", "global_incident_projections", "mode_local_amplitude_scale",
                     "plane_electric_scale", "plane_magnetic_scale", "mode_power_operation_scale")})
                expected[label + "_plane_electric"] = [532, 3]
                expected[label + "_plane_magnetic"] = [532, 3]
    return expected


def validate_array_inventory(report, stage):
    descriptors = report.get("artifacts", {})
    expected = expected_array_shapes(report, stage)
    require(set(expected).issubset(descriptors) and {"full_mpc_masters", "full_mpc_coefficients", "original_port_C_data",
        "original_port_C_indices", "original_port_D_data", "original_port_D_indices"}.issubset(descriptors),
        "complete direct original raw/array/factor/output inventory is missing")
    itemsize = {"complex128": 16, "float64": 8, "int32": 4, "int64": 8, "uint8": 1, "uint32": 4,
                "uint64": 8, "bool": 1, "int8": 1, "float32": 4}
    for name, descriptor in descriptors.items():
        shape, dtype = descriptor.get("shape"), descriptor.get("dtype")
        require(isinstance(name, str) and isinstance(shape, list) and all(type(n) is int and n >= 0 for n in shape)
            and dtype in itemsize and type(descriptor.get("payload_bytes")) is int
            and descriptor["payload_bytes"] == math.prod(shape)*itemsize[dtype]
            and descriptor.get("finite_entries") == math.prod(shape) and descriptor.get("nonfinite_entries") == 0
            and re.fullmatch(r"[0-9a-f]{64}", descriptor.get("file_sha256", ""))
            and isinstance(descriptor.get("path"), str) and not Path(descriptor["path"]).is_absolute(),
            "complete finite typed artifact descriptor required: " + name)
        require(name not in expected or shape == expected[name], "direct artifact exact shape differs: " + name)
    return expected


def validate_direct_event_contract(events, report, stage, *, research_wall_seconds=None, research_memory_gib=None):
    selected_cap = direct_memory_cap(report.get("direct_profile"), stage, research_wall_seconds, research_memory_gib)
    metadata = reviewed_direct_profile_metadata(report.get("direct_profile"))
    require(isinstance(events, list) and events, "nonempty actual ordered events required")
    gates = {}
    for name in ("direct_fresh_carrier_qualification_complete", "direct_complete_original_operator_qualification",
                 "shared_complete_equivalence_before_any_factor", "direct_complete_original_qualification_before_any_factor"):
        positions = [i for i, event in enumerate(events) if event.get("event") == name]
        require(len(positions) == 1, "exactly one complete pre-factor event required: " + name)
        gates[name] = positions[0]
    boundary = gates["direct_complete_original_qualification_before_any_factor"]
    require(all(index < boundary for name, index in gates.items() if name != "direct_complete_original_qualification_before_any_factor"),
            "fresh raw, exhaustive operator and shared gates must precede final admission")
    record = {key: value for key, value in events[boundary].items() if key not in ("event", "worker_elapsed_seconds")}
    require(record == {"operator_receipt": report["original_operator_qualification"],
        "fresh_carrier_receipt": report["fresh_carrier_qualification"], "input_blocks": report["reformed_blocks"], "factor_count": 0},
        "pre-factor complete gate detached from saved original proof")
    admitted, created, retained = [], [], []
    for index, event in enumerate(events):
        name = event.get("event")
        if name == "allocation_admission" and event.get("boundary", "").startswith("quotient_factor_q_"):
            q, facts = len(admitted), event.get("facts", {})
            allowance = (metadata.ny - q)*metadata.factor_allowance_per_q_bytes
            require(stage == "solve" and index > boundary and q < metadata.ny
                and event["boundary"] == f"quotient_factor_q_{q}" and len(retained) == q
                and facts.get("retained_factor_count") == q and facts.get("LU_fill_and_workspace_unknown") is True
                and facts.get("factor_workspace_allowance_bytes") == allowance
                and event.get("remaining_factor_allowance_bytes") == allowance and event.get("admitted") is True,
                "ordered actual fresh q factor allowance/retention admission differs")
            current, payload, workspace, reserve = (event.get(key) for key in
                ("current_tree_rss_bytes", "additional_payload_bytes", "declared_workspace_bytes", "evidence_reserve_bytes"))
            require(all(type(v) is int and v >= 0 for v in (current, payload, workspace, reserve))
                and current > 0 and reserve >= RESERVE_BYTES
                and event.get("projected_tree_bytes") == current + payload + workspace + allowance + reserve
                and event["projected_tree_bytes"] < event.get("effective_tree_cap_bytes", 0) <= selected_cap,
                "actual current RSS plus all q payload/workspace/reserve must fit strict cap")
            descriptors = report["artifacts"]
            csr_bytes = sum(descriptors[f"q_{q}_S_{part}"]["payload_bytes"] for part in ("data", "indices", "indptr"))
            require(payload == 3*csr_bytes and workspace == 2*csr_bytes, "factor gate must bind five actual CSR byte copies")
            admitted.append(q)
        elif name == "all_branch_factor_created":
            q = len(created)
            require(stage == "solve" and index > boundary and q < metadata.ny and event.get("q") == q
                and admitted == list(range(q + 1)) and event.get("factor_count") == q + 1
                and event.get("retained_factor_count") == q + 1
                and event.get("input_CSR_sha256") == report["reformed_blocks"][q]["CSR_sha256"], "created factor input/event identity differs")
            created.append(q)
        elif name == "all_branch_factor_retained":
            q = len(retained)
            require(stage == "solve" and index > boundary and q < metadata.ny and event.get("q") == q
                and created == list(range(q + 1)) and event.get("retained_factor_count") == q + 1,
                "every actual factor must remain simultaneously retained")
            if metadata.name == "Y":
                require(event.get("remaining_declared_allowance_bytes")
                    == (metadata.ny-q-1)*metadata.factor_allowance_per_q_bytes
                    and event.get("factor_memory_bytes") is None,
                    "Y retained factor event must preserve the exact remaining allowance and unknown fill")
            retained.append(q)
        elif stage == "prefactor" and name in ("all_branch_factor_test", "original_augmented_manufactured_control"):
            raise ValueError("prefactor executed forbidden factor/solve control")
    require((stage == "prefactor" and not admitted and not created and not retained)
        or (stage == "solve" and admitted == created == retained == list(range(metadata.ny))), "all q factor event inventory incomplete")
    return True


def validate_gauss(primary, literal):
    names = {"top/0", "top/1", "bottom/0", "bottom/1"}
    require(set(primary) == names and set(literal) == {gauge+"/"+name for gauge in ("global_z", "boundary_plane") for name in names},
            "complete four primary and eight independent literal Gauss identities required")
    for name in primary:
        require(all(primary[name].get("rules") == literal[gauge+"/"+name].get("rules") for gauge in ("global_z", "boundary_plane")),
                "literal/primary compiled Gauss rules differ")
        rules = primary[name]["rules"]
        require(len(rules) == 1 and rules[0].get("degree") == 23
            and rules[0].get("facet_cell") == "quadrilateral" and rules[0].get("integral_type") == "exterior_facet"
            and rules[0].get("points", {}).get("shape") == [144, 2]
            and rules[0].get("weights", {}).get("shape") == [144]
            and rules[0]["points"].get("dtype") == rules[0]["weights"].get("dtype") == "float64",
            "unchanged Gauss23/144-node compiled rules required")
        for identity in (primary[name], literal["global_z/"+name], literal["boundary_plane/"+name]):
            kernel = identity.get("loaded_kernel", {})
            require(kernel.get("schema") == "task40extra.loaded-surface-kernel.v1", "actual loaded kernel provenance required")
            for path_key, hash_key in (("module_path", "binary_sha256"), ("module_bound_C_path", "module_bound_C_sha256")):
                path, sha = kernel.get(path_key), kernel.get(hash_key)
                require(isinstance(path, str) and Path(path).is_absolute() and re.fullmatch(r"[0-9a-f]{64}", sha or "")
                        and file_sha(path) == sha, "actual current primary/literal binary/generated-C hash differs")
    return True


def validate_spool_manifest(manifest, *, literal, count, indices, storage, profile):
    require(manifest.get("schema") == ("task40extra.direct-literal-current-mode-spool.v1" if literal
        else "task40extra.lossless-raw-packet-spool.v1")
        and manifest.get("status") == ("READY_LITERAL_CONTROLS_UNQUALIFIED" if literal else "READY_RAW_PACKETS_UNQUALIFIED")
        and manifest.get("expected_mode_count") == manifest.get("recorded_mode_count") == count
        and manifest.get("factor_count") == 0 and manifest.get("PDE_solved") is False,
        "complete fresh finite primary/literal manifest required")
    records = manifest.get("records", [])
    require(len(records) == count and [r.get("local_mode_index") for r in records] == list(range(count))
        and [r.get("original_mode_index") for r in records] == indices, "every current primary/literal original alias exactly once required")
    if literal:
        require(manifest.get("original_mode_indices") == indices and manifest.get("ownership_range") == [0, storage]
            and manifest.get("literal_controls_qualified") is False and manifest.get("all_mode_dense_cache") is False,
            "literal controls are lossless independent witnesses, not a qualification status")
    else:
        require(manifest.get("raw_port_qualified") is False and manifest.get("complete_finite_stream") is True
            and manifest.get("all_finite") is True and manifest.get("failure") is None
            and all(record.get("all_finite") is True for record in records)
            and manifest.get("direct_profile_metadata") == profile, "raw spool finite/profile/lifecycle identity differs")
    return True


def validate_same_live_carrier_chain(events, report):
    fresh = report["fresh_carrier_qualification"]
    metadata = reviewed_direct_profile_metadata(report.get("direct_profile"))
    expected = {"global": fresh["global_carrier_identity_before"], "local": fresh["local_carrier_identities"]}
    require(fresh["global_carrier_identity_after"] == expected["global"] and len(expected["local"]) == metadata.replication_count
        and report.get("same_live_carrier_identity_before_factor") == report.get("same_live_carrier_identity_at_exit") == expected,
        "fresh/current pre-factor/exit same-live carrier chain differs")
    positions = [i for i, item in enumerate(events) if item.get("event") == "direct_same_live_carrier_identity"]
    records = [events[i] for i in positions]
    require(len(records) == 2 and [item.get("boundary") for item in records] == ["before_all_q_factors", "before_successful_exit"]
        and all(item.get("unchanged") is True and item.get("actual") == item.get("expected") == expected for item in records),
        "both actual live numeric carrier events are required")
    proof = next(i for i, item in enumerate(events) if item.get("event") == "direct_complete_original_qualification_before_any_factor")
    require(positions[0] < proof < positions[1] and all(positions[0] < i < positions[1]
        for i, item in enumerate(events) if item.get("event") in ("all_branch_factor_created", "all_branch_factor_retained")),
        "same-live chain must surround all q factors and original successful exit")
    return True


def decode_metadata(value):
    if isinstance(value, dict):
        if set(value) == {"__raw_spool_complex__"}:
            return complex(*value["__raw_spool_complex__"])
        require("__raw_spool_nonfinite__" not in value and "measurement_status" not in value,
                "failed/nonfinite diagnostic cannot become qualified data")
        if set(value) == {"real", "imag"}:
            return complex(value["real"], value["imag"])
        return {key: decode_metadata(member) for key, member in value.items()}
    if isinstance(value, list):
        return [decode_metadata(member) for member in value]
    return value


class SavedRun:
    """Hash-bound readonly mmap loader; finite checks use bounded panels."""
    def __init__(self, directory, descriptors, allocation_gate, environment):
        self.directory, self.descriptors = Path(directory).resolve(), descriptors
        self.gate, self.environment = allocation_gate, environment
        self.paths = {value["path"]: name for name, value in descriptors.items()}
        require(len(self.paths) == len(descriptors), "each named array must have its own unambiguous descriptor path")

    def json(self, reference):
        path = bound_path(self.directory, reference["path"])
        sha = reference.get("file_sha256", reference.get("sha256"))
        self.gate("direct_checker_JSON_" + path.name, {"matrix_payload_bytes": 0,
            "workspace_bytes": 8*path.stat().st_size + (1 << 20)})
        require(file_sha(path) == sha, "current receipt/ledger JSON file hash differs")
        return json.loads(path.read_text())

    def descriptor(self, reference):
        require(reference.get("path") in self.paths, "raw/literal array is absent from the complete current manifest")
        name = self.paths[reference["path"]]
        validate_descriptor_metadata(reference, self.descriptors[name])
        value = self.load(name)
        if "array_sha256" in reference:
            self.gate("direct_checker_descriptor_payload_hash_" + name,
                {"matrix_payload_bytes": 0, "workspace_bytes": 2 << 20})
        validate_descriptor_payload(reference, self.descriptors[name], value)
        return value

    def load(self, name):
        import numpy as np
        descriptor = self.descriptors[name]
        path = bound_path(self.directory, descriptor["path"])
        self.gate("direct_checker_mmap_" + name, {"matrix_payload_bytes": descriptor["payload_bytes"], "workspace_bytes": 1 << 20})
        require(file_sha(path) == descriptor["file_sha256"], "current saved artifact file hash differs: " + name)
        value = np.load(path, allow_pickle=False, mmap_mode="r")
        require(not value.dtype.hasobject and not value.flags.writeable and list(value.shape) == descriptor["shape"]
            and str(value.dtype) == descriptor["dtype"] and value.nbytes == descriptor["payload_bytes"], "readonly typed mmap identity differs")
        flat = value.ravel(order="K")
        require(all(np.isfinite(flat[start:start+65536]).all() for start in range(0, flat.size, 65536)),
                "nonfinite saved numeric witness")
        return value

    def reference(self, reference):
        import numpy as np
        require(reference.get("descriptor") == self.descriptors.get(reference.get("artifact")), "operator witness descriptor differs from manifest")
        value = self.load(reference["artifact"])
        require(list(value.shape) == reference["shape"] and value.dtype.str == reference["dtype"]
            and hashlib.sha256(memoryview(np.ascontiguousarray(value)).cast("B")).hexdigest() == reference["numeric_sha256"],
            "complete original numeric tensor/map hash differs")
        return value

    def csr(self, prefix, shape, *, csc=False):
        import numpy as np
        from scipy import sparse
        from src.solvers.y_orbit_sparse_reference import integer_admission, csr_audit
        data, indices, indptr = (self.load(prefix + "_" + member) for member in ("data", "indices", "indptr"))
        for dtype in (indices.dtype, self.environment["petsc_int_type"], "int32"):
            integer_admission(shape, len(data), index_dtype=dtype, indptr_dtype=indptr.dtype)
        count, bound = (shape[1] + 1, shape[0]) if csc else (shape[0] + 1, shape[1])
        require(data.ndim == 1 and data.dtype == np.dtype("complex128") and indices.shape == data.shape
            and indices.dtype.kind in "iu" and indptr.dtype.kind in "iu" and indptr.shape == (count,)
            and indptr[0] == 0 and indptr[-1] == len(data) and np.all(np.diff(indptr) >= 0)
            and np.all(indices >= 0) and np.all(indices < bound), "actual CSR/CSC wide indices/pointers fail before narrowing")
        for row in range(count - 1):
            segment = indices[int(indptr[row]):int(indptr[row+1])]
            require(np.all(np.diff(segment) > 0), "current CSR/CSC must be strictly sorted without duplicate aggregation")
        constructor = sparse.csc_matrix if csc else sparse.csr_matrix
        matrix = constructor((data, indices, indptr), shape=shape, copy=False)
        if not csc:
            csr_audit(matrix, petsc_index_dtype=self.environment["petsc_int_type"])
        return matrix


class EntityMap:
    """Complete original row maps with one retained template/inverse per state."""
    def __init__(self, source, saved):
        import numpy as np
        self.saved, self.source = saved, source
        self.ny, self.width = source["entities"]["ny"], source["entities"]["width"]
        self.n = self.ny*self.width
        self.rows, self.templates = [], {}
        saved.gate("direct_checker_streamed_entity_maps", {"matrix_payload_bytes": self.n*8, "workspace_bytes": 4 << 20})
        covered, canonical = set(), set()
        for record in source["entities"]["records"]:
            rows = saved.reference(record["rows"])
            start, size = record["orbit"]*self.width + record["first"], record["size"]
            key = record["matrix"]["numeric_sha256"]
            if key not in self.templates:
                saved.gate("direct_checker_original_entity_state", {"matrix_payload_bytes": 2*size*size*16,
                    "workspace_bytes": 4*size*size*16})
                matrix = saved.reference(record["matrix"])
                inverse = np.linalg.inv(matrix)
                require(matrix.shape == inverse.shape == (size, size)
                    and np.linalg.norm(inverse@matrix - np.eye(size))/math.sqrt(size) <= 1e-11,
                    "complete original coefficient inverse gate differs")
                self.templates[key] = matrix, inverse
            require(len(rows) == size and 0 <= start <= self.n-size and not covered.intersection(map(int, rows))
                and not canonical.intersection(range(start, start+size)), "complete unique original entity row/channel partition differs")
            covered.update(map(int, rows)); canonical.update(range(start, start+size))
            self.rows.append((rows, slice(start, start+size), key))
        require(covered == canonical == set(range(self.n)), "all actual FE channels must survive entity maps")

    def apply(self, value, direction):
        import numpy as np
        require(value.shape == (self.n,), "full original entity input shape differs")
        self.saved.gate("direct_checker_entity_vector", {"matrix_payload_bytes": self.n*16, "workspace_bytes": 108*16})
        result = np.zeros(self.n, complex)
        for rows, canonical, key in self.rows:
            matrix, inverse = self.templates[key]
            if direction.endswith("to_canonical"):
                data = value[rows]
                operator = inverse if direction == "primal_to_canonical" else (matrix.conj().T if direction == "dual_to_canonical" else matrix.T)
                if np.any(data != 0): result[canonical] = operator@data
            else:
                data = value[canonical]
                operator = matrix if direction == "primal_from_canonical" else (inverse.conj().T if direction == "dual_from_canonical" else inverse.T)
                if np.any(data != 0): result[rows] = operator@data
        return result

    def modal(self, value, *, dual, etas):
        import numpy as np
        canonical = self.apply(value, "dual_to_canonical" if dual else "primal_to_canonical").reshape(self.ny, self.width)
        result = np.empty_like(canonical)
        for q, eta in enumerate(etas):
            result[q] = sum(np.conjugate(eta)**j*canonical[j] for j in range(self.ny))/math.sqrt(self.ny)
        return result


def relative(error, reference):
    import numpy as np
    numerator, denominator = float(np.linalg.norm(error)), float(np.linalg.norm(reference))
    return numerator/denominator if denominator else (0.0 if numerator == 0 else float("inf"))


def operation_error(error, scale):
    import numpy as np
    require(error.shape == scale.shape and error.size == 532 and np.isfinite(error).all() and np.isfinite(scale).all()
        and np.all(error >= 0) and np.all(scale >= 0) and not np.any((scale == 0) & (error != 0)),
        "every original532 mode needs its own finite operation scale")
    return float(np.max(np.divide(error, scale, out=np.zeros_like(error), where=scale != 0)))


def check_raw_carriers(receipt, *, saved, global_map, local_maps, physical_modes, cfg, original_c, original_d, operator_receipt, add):
    """Reconstruct one primary/literal mode at a time, without a dense collection."""
    import numpy as np
    from src.solvers.dtn_port_3d import _traction_vector
    from src.solvers.dtn_boundary_phase_gauge import incident_projection_in_solver_coordinates, BOUNDARY_PLANE
    from src.solvers.dtn_boundary_phase_gauge import assembly_projection_denominator
    from src.solvers.fullspace_dtn_action import _jsonable, build_ordered_mode_manifest
    require(receipt.get("schema") == CARRIER_SCHEMA and receipt.get("status") == "PASS_DIRECT_FRESH_CARRIER_COMPONENTS_ONLY"
        and receipt.get("fresh_primary_and_literal_forms") is True and receipt.get("snapshots_reused") is False
        and receipt.get("full_Ny_reference_matrices_created") is False and receipt.get("factor_count") == 0
        and receipt.get("original532_alias_union_exactly_once") is True, "complete fresh component receipt required")
    validate_profile(receipt.get("profile"))
    metadata = reviewed_direct_profile_metadata(receipt["profile"]["name"])
    require(receipt.get("qualification_source_sha256") == saved_source(saved, "src/solvers/y_orbit_direct_carrier_qualification.py"),
            "fresh carrier qualification source differs")
    inventory = receipt["global_inventory"]
    keys = [[i, m.side, int(m.m), int(m.n), m.polarization] for i, m in enumerate(physical_modes)]
    physical_rows, _, physical_digest = build_ordered_mode_manifest(physical_modes, cfg)
    require(physical_digest == PHYSICAL_MANIFEST, "original physical mode details differ from complete manifest")
    require(inventory.get("ordered_mode_keys") == keys and inventory.get("q_port_counts") == list(metadata.q_port_counts)
        and inventory.get("physical_generator_manifest_sha256") == PHYSICAL_MANIFEST, "physically regenerated complete alias inventory differs")
    sector_indices = validate_direct_mode_roles(physical_modes, metadata.name)
    controls = [saved.json(receipt["global_component_receipt"])] + [saved.json(item) for item in receipt["local_raw_receipts"]]
    raw_manifests = [saved.json(item) for item in receipt["raw_spool_manifests"]]
    literals = [saved.json(item) for item in receipt["literal_mode_manifests"]]
    require(len(controls) == len(raw_manifests) == len(literals) == metadata.replication_count+1, "full and every fresh twist required")
    folds = receipt.get("complete_mode_fold_lift", [])
    require(len(folds) == metadata.replication_count
        and len(receipt.get("cell_metric_material_cover", [])) == metadata.replication_count
        and [item.get("twist_index") for item in receipt["local_raw_receipts"]] == list(range(metadata.replication_count)),
        "both fresh local raw/fold/actual-cell qualification inventories are required")
    for twist, fold in enumerate(folds):
        indices = sector_indices[twist]
        require(fold.get("mode_count") == metadata.sector_port_counts[twist] and fold.get("original_mode_indices") == indices
            and fold.get("tolerance") == 1e-10 and all(fold.get(key) is True for key in
                ("raw_and_both_actual_cutoffs_audited", "complete_DOF_fold_and_lift", "single_D_conjugation", "nonzero_lower_dual_rhs_sqrtK_identity")),
            "complete raw/after-component/stored fold ledger inventory differs")
        finite_gate(fold.get("maximum_complete_mode_relative_error"), 1e-10, "complete fold maximum")
        require(set(fold.get("rank_one_bounds_by_stage", {})) == {"raw", "after_component_mask", "stored"}, "every actual cutoff stage required")
        for value in fold["rank_one_bounds_by_stage"].values(): finite_gate(value, 1e-10, "complete fold rank-one")
        ledger = bound_path(saved.directory, fold["ledger"]["path"])
        saved.gate("direct_checker_stream_complete_fold_ledger", {"matrix_payload_bytes": 0, "workspace_bytes": 2 << 20})
        require(file_sha(ledger) == fold["ledger"]["file_sha256"], "complete current fold ledger hash differs")
        count = 0
        with ledger.open() as stream:
            for line in stream:
                if not line.strip(): continue
                row = json.loads(line)
                require(count < len(indices) and row.get("original_mode_index") == indices[count]
                    and row.get("original_mode_key") == keys[indices[count]][1:]
                    and row.get("local_mode_index") == count and row.get("twist_index") == twist
                    and row.get("local_branch_index") == ((int(physical_modes[indices[count]].n)-twist)//metadata.replication_count)%2
                    and row.get("status") == "PASS_COMPLETE_MODE_FOLD_LIFT_CUTOFF"
                    and set(row.get("stages", {})) == {"raw", "after_component_mask", "stored"},
                    "complete current fold ledger alias/stage/index identity differs")
                for stage in row["stages"].values():
                    for name in ("C", "D"):
                        for key in ("fold_relative_error", "lift_relative_error"):
                            finite_gate(stage[name].get(key), 1e-10, "fold ledger "+key)
                    finite_gate(stage.get("lifted_rank_one_relative_bound"), 1e-10, "fold ledger rank-one")
                for key, value in row["H"].items():
                    if key.endswith("relative_error"): finite_gate(value, 1e-10, "fold ledger H")
                finite_gate(row["nonzero_lower_dual_rhs"].get("scaled_identity_relative_error"), 1e-10, "fold ledger lower RHS")
                for role in ("global_cutoff_losses", "local_cutoff_losses"):
                    for value in row[role]["relative_rank_one_bounds"].values(): finite_gate(value, 1e-10, "fold ledger cutoff loss")
                count += 1
        require(count == len(indices), "complete fold ledger cannot omit any actual physical alias")
    contexts, Hs = {}, []
    saved.gate("direct_checker_literal_incident_rhs", {"matrix_payload_bytes": 3*metadata.storage_rows*16, "workspace_bytes": 1 << 20})
    raw_incident_rhs, incident_base = np.zeros(metadata.storage_rows, complex), None

    def dense(pair, n):
        rows, values = pair
        require(rows.dtype.kind in "iu" and values.dtype == np.dtype("complex128") and rows.shape == values.shape
            and np.all(rows >= 0) and np.all(rows < n) and np.all(np.diff(rows) > 0) and np.isfinite(values).all(),
            "lossless current sparse pair support/values differ")
        result = np.zeros(n, complex); result[rows] = values
        return result

    def primary(manifest, index, n):
        record = manifest["records"][index]
        descriptor = saved.json({"path": record["descriptor_path"], "file_sha256": record["descriptor_sha256"]})
        require(descriptor.get("all_finite") is True and descriptor.get("raw_failure_diagnostic_only") is False,
                "raw nonfinite/failed descriptor cannot qualify")
        rows, values = (saved.descriptor(descriptor["sparse_payload"][key]) for key in ("rows", "values"))
        require(rows.dtype == np.dtype("int64") and values.dtype == np.dtype("complex128"), "raw lossless typed sparse arrays required")
        pairs, cursor = {}, 0
        offsets = descriptor["offset_inventory"]
        require(len(offsets) == len(PAIR_FIELDS), "all ten original raw/component/stored pairs required")
        for field, item in zip(PAIR_FIELDS, offsets, strict=True):
            length = item.get("length")
            require(item.get("field") == field and item.get("offset") == cursor and type(length) is int and length >= 0
                and cursor+length <= len(rows), "exact raw sparse offsets cannot overlap or omit coefficients")
            pairs[field] = dense((rows[cursor:cursor+length], values[cursor:cursor+length]), n); cursor += length
        require(cursor == len(rows) == len(values), "raw payload complete offset coverage required")
        packet = decode_metadata(descriptor["metadata"])
        return packet, pairs

    def literal(manifest, index, n):
        descriptor = saved.json(manifest["records"][index])
        rows, values = (saved.descriptor(descriptor["literal_payload"][key]) for key in ("rows", "values"))
        result, cursor = {}, 0
        require(len(descriptor["offset_inventory"]) == 2, "independent literal C and D controls required")
        for field, item in zip(("C", "D"), descriptor["offset_inventory"], strict=True):
            length = item.get("length")
            require(item.get("field") == field and item.get("offset") == cursor and type(length) is int and length >= 0
                and cursor+length <= len(rows), "literal exact-nonzero offsets differ")
            result[field] = dense((rows[cursor:cursor+length], values[cursor:cursor+length]), n); cursor += length
        require(cursor == len(rows) == len(values) and descriptor.get("literal_binding_sha256") == canonical_digest(manifest["frozen_literal_binding"]),
                "literal full coefficient/source/kernel binding differs")
        return descriptor, result

    def masks(packet, pairs, mode, H, role):
        require(packet.get("single_D_conjugation") is True and packet.get("raw_vectors_destroyed_before_callback") is True,
                "original single D conjugation/MPC lifecycle required")
        traction = _traction_vector(mode, cfg)
        raw_expected = {"C": -traction[0]*pairs["raw_component_0"]-traction[1]*pairs["raw_component_1"],
            "D": np.conjugate(mode.e_vector[0]*pairs["raw_component_0"]+mode.e_vector[1]*pairs["raw_component_1"])}
        for name in ("C", "D"):
            add(role+"_raw_component_"+name, relative(pairs["raw_"+name]-raw_expected[name], raw_expected[name]), 1e-10)
        for j in range(2):
            raw, actual = pairs[f"raw_component_{j}"], pairs[f"component_masked_entries_{j}"]
            threshold = max(1e-30, 1e-13*float(np.max(np.abs(raw))))
            expected = np.where(np.abs(raw) > threshold, raw, 0)
            diagnostic = packet["component_masks"][j]
            require(diagnostic["threshold"] == threshold and diagnostic["absolute_sparse_floor"] == 1e-30
                and diagnostic["relative_sparse_cutoff"] == 1e-13 and np.array_equal(actual != 0, expected != 0),
                "actual component cutoff policy/support differs")
            add(role+f"_component_cutoff_{j}", relative(actual-expected, expected), 1e-10)
        cx, cy = pairs["component_masked_entries_0"], pairs["component_masked_entries_1"]
        combined = {"C": -traction[0]*cx-traction[1]*cy, "D": np.conjugate(mode.e_vector[0]*cx+mode.e_vector[1]*cy)}
        for j, name in enumerate(("C", "D")):
            actual = pairs["stored_"+name+"_sparse"]
            threshold = max(1e-30, 1e-13*float(np.max(np.abs(combined[name]))))
            expected = np.where(np.abs(combined[name]) > threshold, combined[name], 0)
            diagnostic = packet["combination_masks"][j]["combination_stage"]
            require(diagnostic["threshold"] == threshold and diagnostic["absolute_sparse_floor"] == 1e-30
                and diagnostic["relative_sparse_cutoff"] == 1e-13 and np.array_equal(actual != 0, expected != 0),
                "actual final C/D cutoff policy/support differs")
            add(role+"_after_component_"+name, relative(pairs["after_component_mask_"+name]-combined[name], combined[name]), 1e-10)
            add(role+"_final_cutoff_"+name, relative(actual-expected, expected), 1e-10)
        stages = {"raw": {key: pairs["raw_"+key] for key in ("C", "D")},
            "after_component_mask": {key: pairs["after_component_mask_"+key] for key in ("C", "D")},
            "stored": {key: pairs["stored_"+key+"_sparse"] for key in ("C", "D")}}
        for label, before, after in (("component", "raw", "after_component_mask"), ("final", "after_component_mask", "stored"), ("all", "raw", "stored")):
            C, D, Cr, Dr = stages[after]["C"], stages[after]["D"], stages[before]["C"], stages[before]["D"]
            loss = (np.linalg.norm(C-Cr)*np.linalg.norm(D)+np.linalg.norm(Cr)*np.linalg.norm(D-Dr))/H
            reference = np.linalg.norm(stages["raw"]["C"])*np.linalg.norm(stages["raw"]["D"])/H
            add(role+"_"+label+"_lost_rank_one", float(loss/reference) if reference else (0. if loss == 0 else float("inf")), 1e-10)
        return stages

    for role_index, (control, raw, lit) in enumerate(zip(controls, raw_manifests, literals, strict=True)):
        twist, n = (None, metadata.storage_rows) if role_index == 0 else (role_index-1, metadata.local_storage_rows)
        role = "full" if twist is None else f"twist_{twist}"
        indices = list(range(532)) if twist is None else sector_indices[twist]
        if twist is not None:
            require(np.array_equal(saved.reference(operator_receipt["local_condensation"][twist]["port_original_indices"]), indices),
                    "complete same-live local entries must preserve all original physical indices")
        validate_spool_manifest(raw, literal=False, count=len(indices), indices=indices, storage=n, profile=receipt["profile"])
        validate_spool_manifest(lit, literal=True, count=len(indices), indices=indices, storage=n, profile=receipt["profile"])
        qualification_path = "src/solvers/dtn_boundary_plane_qualification.py" if twist is None else "src/solvers/y_orbit_quotient_raw_qualification.py"
        require(control.get("qualification_source_sha256") == saved_source(saved, qualification_path)
            and control.get("status") == ("PASS_COMPONENT_ONLY" if twist is None else "PASS_QUOTIENT_RAW_PORT_AUDIT_ONLY")
            and control.get("tolerance") == 1e-10 and control.get("seed") == 4053202
            and len(control.get("per_mode", [])) == len(indices), "full fresh source-bound complete component ledger required")
        expected_identity = receipt["global_carrier_identity_before"] if twist is None else receipt["local_carrier_identities"][twist]
        if twist is None:
            require(control.get("identity") == expected_identity
                and control.get("carrier_digest_before") == control.get("carrier_digest_after") == expected_identity["carrier_numeric_sha256"],
                "fresh global component receipt drifted from actual same-live carrier")
        else:
            require(control.get("carrier_identity_before") == control.get("carrier_identity_after") == expected_identity,
                    "fresh local raw qualification receipt drifted from actual same-live carrier")
        binding = lit["frozen_literal_binding"]
        require(binding["qualification_source_sha256"] == control["qualification_source_sha256"], "literal qualification source differs")
        validate_gauss(binding["primary_compiled_gauss"], binding["literal_compiled_gauss"])
        require(binding["literal_compiled_gauss"] == control["independent_oracle_compiled_gauss"], "literal compiled kernel differs from receipt")
        Hs.append([record["literal_H"] for record in lit["records"]])
        component_hashes = {}
        for index, original in enumerate(indices):
            saved.gate("direct_checker_complete_raw_literal_mode", {"matrix_payload_bytes": 24*n*16,
                "workspace_bytes": 32*metadata.storage_rows*16 + (4 << 20), "all_mode_dense_cache": False,
                "global_and_local_current_mode_fold_scratch_included": True})
            packet, pairs = primary(raw, index, n)
            literal_packet, literal_vectors = literal(lit, index, n)
            require(packet["local_mode_index"] == literal_packet["local_mode_index"] == index
                and packet["original_mode_index"] == literal_packet["original_mode_index"] == original
                and packet["original_mode_key"] == literal_packet["original_mode_key"] == keys[original][1:]
                and packet["ownership_range"] == literal_packet["ownership_range"] == [0, n]
                and packet["quotient_twist_index"] == literal_packet["quotient_twist_index"] == twist
                and packet["assembly_context_sha256"] == literal_packet["assembly_context_sha256"] == binding["assembly_context_sha256"]
                and canonical_digest(packet["assembly_context"]) == packet["assembly_context_sha256"], "primary/literal actual current context/mode identity differs")
            branch = None if twist is None else ((int(physical_modes[original].n)-twist)//metadata.replication_count)%2
            require(packet["local_branch_index"] == literal_packet["local_branch_index"] == branch
                and packet["quotient_contract_sha256"] == literal_packet["quotient_contract_sha256"] == binding["quotient_contract_sha256"]
                and packet["physical_generator_manifest_sha256"] == literal_packet["physical_generator_manifest_sha256"] == PHYSICAL_MANIFEST
                and canonical_digest(packet["original_mode_row"]) == canonical_digest(physical_rows[original]),
                "original physical mode/e/k/denominator details or explicit alias branch changed")
            if role not in contexts: contexts[role] = _jsonable(packet["assembly_context"])
            require(contexts[role] == _jsonable(packet["assembly_context"]), "complete stream changed actual discrete context")
            require(contexts[role]["gauss"]["compiled_forms_verified"] == binding["primary_compiled_gauss"]
                and _jsonable(control.get("raw_discrete_context")) == contexts[role],
                "actual raw stream, component receipt and primary loaded Gauss context differ")
            mode = physical_modes[original]
            component_key = (mode.side, int(mode.m), int(mode.n))
            hashes = tuple(hashlib.sha256(memoryview(pairs[f"raw_component_{j}"]).cast("B")).hexdigest() for j in range(2))
            previous = component_hashes.setdefault(component_key, (hashes, 0))
            require(previous[0] == hashes, "independent s/p weights cannot change their shared actual component forms")
            component_hashes[component_key] = (hashes, previous[1]+1)
            H = literal_packet["literal_H"]; finite_gate(H, float("inf"), role+"_H"); require(H > 0, "positive literal H required")
            expected_h = assembly_projection_denominator(physical_modes[original], cfg, BOUNDARY_PLANE)/(1 if twist is None else metadata.replication_count)
            add(role+f"_m{original}_physical_H", abs(H-expected_h)/expected_h, 1e-10)
            add(role+f"_m{original}_literal_H", abs(packet["local_plane_H"]-H)/H, 1e-10)
            for name in ("C", "D"):
                add(role+f"_m{original}_primary_literal_"+name, relative(pairs["raw_"+name]-literal_vectors[name], literal_vectors[name]), 1e-10)
            stages = masks(packet, pairs, physical_modes[original], H, role+f"_m{original}")
            source = global_map.source if twist is None else local_maps[twist].source
            slaves, independent = saved.reference(source["native"]["slaves"]), saved.reference(source["native"]["independent"])
            require(all(np.all(vector[slaves] == 0) for stage in stages.values() for vector in stage.values()), "all raw/stored actual MPC slave rows must be zero")
            if twist is None:
                incident_p = incident_projection_in_solver_coordinates(physical_modes[original], cfg, BOUNDARY_PLANE)
                raw_incident_rhs += stages["raw"]["C"]*incident_p
                mode = physical_modes[original]
                if mode.side == "top" and int(mode.m) == int(mode.n) == 0 and incident_base is None:
                    k_inc = np.asarray(cfg.wavevector, dtype=complex)
                    e_inc = complex(cfg.incident_amplitude)*np.asarray(cfg.polarization_vector, dtype=complex)
                    traction = np.cross(1j*np.cross(k_inc, e_inc), np.asarray([0., 0., 1.]))
                    incident_base = (traction[0]*pairs["raw_component_0"]+traction[1]*pairs["raw_component_1"])*np.exp(1j*k_inc[2]*cfg.physical_z_max)
                c = np.zeros(n, complex); start, stop = original_c.indptr[original:original+2]
                c[original_c.indices[start:stop]] = original_c.data[start:stop]
                d = np.zeros(n, complex); start, stop = original_d.indptr[original:original+2]
                d[original_d.indices[start:stop]] = original_d.data[start:stop]
                add(f"full_m{original}_original_C_binding", relative(c-stages["stored"]["C"], c), 1e-11)
                add(f"full_m{original}_original_D_binding", relative(d-stages["stored"]["D"], d), 1e-11)
            else:
                entry = operator_receipt["local_condensation"][twist]["carrier_entries"][index]
                require(entry["port"] == index and entry["mode_key"] == [index, *keys[original][1:]]
                    and entry["H"] == H, "original condensed entry changed the fresh original mode/normalization")
                for name, row_key, value_key in (("C", "coupling_rows", "coupling_values"), ("D", "projection_rows", "projection_values")):
                    vector = dense((saved.reference(entry[row_key]), saved.reference(entry[value_key])), n)
                    add(f"twist_{twist}_m{original}_same_live_stored_"+name,
                        relative(vector-stages["stored"][name], stages["stored"][name]), 1e-11)
                gp, gpair = primary(raw_manifests[0], original, metadata.storage_rows)
                global_stages = masks(gp, gpair, physical_modes[original], Hs[0][original], f"fold_m{original}")
                global_rows = saved.reference(global_map.source["native"]["independent"])
                tau = complex(*receipt_transport_eta(global_map.source, cfg, twist))**2
                for stage in ("raw", "after_component_mask", "stored"):
                    lifted = {}
                    for name in ("C", "D"):
                        functional = name == "D"
                        direction = "functional" if functional else "dual"
                        gc = global_map.apply(global_stages[stage][name][global_rows], direction+"_to_canonical").reshape(metadata.ny, metadata.rows_per_q)
                        lc = local_maps[twist].apply(stages[stage][name][independent], direction+"_to_canonical").reshape(2, metadata.rows_per_q)
                        phase = tau if functional else np.conjugate(tau)
                        folded = local_maps[twist].apply((sum(phase**replica*gc[2*replica:2*replica+2]
                            for replica in range(metadata.replication_count))/metadata.replication_count).reshape(-1), direction+"_from_canonical")
                        add(f"twist_{twist}_m{original}_{stage}_{name}_complete_fold", relative(folded-stages[stage][name][independent], stages[stage][name][independent]), 1e-10)
                        phase = np.conjugate(tau) if functional else tau
                        lifted[name] = global_map.apply(np.concatenate([phase**replica*lc for replica in range(metadata.replication_count)]).reshape(-1), direction+"_from_canonical")
                        add(f"twist_{twist}_m{original}_{stage}_{name}_complete_lift", relative(lifted[name]-global_stages[stage][name][global_rows], global_stages[stage][name][global_rows]), 1e-10)
                    C, D = global_stages[stage]["C"][global_rows], global_stages[stage]["D"][global_rows]
                    loss = np.linalg.norm(lifted["C"]-C)*np.linalg.norm(lifted["D"])+np.linalg.norm(C)*np.linalg.norm(lifted["D"]-D)
                    ref = np.linalg.norm(C)*np.linalg.norm(D)
                    add(f"twist_{twist}_m{original}_{stage}_complete_rank_one", float(loss/ref) if ref else (0. if loss == 0 else float("inf")), 1e-10)
                Hg = Hs[0][original]
                add(f"twist_{twist}_m{original}_H_over_K", abs(Hg/metadata.replication_count-H)/H, 1e-10)
                x = saved.load(f"direct_twist_{twist}_lower_rhs_local_state")
                gx = saved.load(f"direct_twist_{twist}_lower_rhs_global_state")
                lc = local_maps[twist].apply(x, "primal_to_canonical").reshape(2, metadata.rows_per_q)
                lift = global_map.apply(np.concatenate([tau**replica*lc for replica in range(metadata.replication_count)]).reshape(-1)/math.sqrt(metadata.replication_count), "primal_from_canonical")
                add(f"twist_{twist}_m{original}_lower_primal_lift", relative(gx-lift, lift), 1e-11)
                beta, g = complex(1+(original+1)/533, .25), complex(.7, -.13-(original+1)/533)
                lower_global = global_stages["raw"]["D"][global_rows]@gx-Hg*beta/math.sqrt(metadata.replication_count)+g
                lower_local = stages["raw"]["D"][independent]@x-H*beta+g/math.sqrt(metadata.replication_count)
                add(f"twist_{twist}_m{original}_nonzero_lower_dual_sqrtK", relative(np.asarray(lower_global/math.sqrt(metadata.replication_count)-lower_local), np.asarray(lower_local)), 1e-10)
            del pairs, stages, literal_vectors
        require(len(component_hashes) == len(indices)//2 and all(item[1] == 2 for item in component_hashes.values()),
                "every original side/m/n component pair must retain both physical polarizations")
    require(incident_base is not None, "original top zero-order incident literal components required")
    return contexts, Hs, incident_base+raw_incident_rhs


def saved_source(saved, path):
    return saved.source["files_sha256"][path]


def receipt_transport_eta(source, cfg, twist):
    import numpy as np
    metadata = reviewed_direct_profile_metadata(source["profile"]["name"])
    require(source["entities"]["ny"] == metadata.ny
        and type(twist) is int and twist in range(metadata.replication_count),
        "transport phase requires an actual reviewed global source and twist")
    eta = np.exp(1j*(complex(cfg.ky).real*float(cfg.period_y)+2*np.pi*twist)/metadata.ny)
    return [float(eta.real), float(eta.imag)]


def check_direct(directory, *, checker_source, checker_environment, stage, allocation_gate, checker_directory=None,
                 research_wall_seconds=None, research_memory_gib=None):
    """Supervised entry point. No live FE constructors or historical arrays."""
    import numpy as np
    from benchmarks.y_orbit_direct_source_contract import load_direct_source_contract
    from benchmarks.check_y_orbit_quotient_probe import check_shared_storage_evidence
    from src.solvers.y_orbit_direct_profile import build_direct_profile_config
    from src.solvers.y_orbit_direct_operator_qualification import check_direct_original_cell_contributions
    from src.solvers.y_orbit_sparse_reference import sparse_hash
    from src.solvers.task40extra_y_orbit_reference import pilot_config
    from src.common.modes_3d import outgoing_port_modes_3d
    from src.solvers.fullspace_dtn_action import _jsonable

    directory = Path(directory).resolve()
    root = Path(__file__).resolve().parents[1]
    artifact_root = root / "benchmarks/artifacts/task40extra_dot_parallel_cloud"
    require(directory.is_relative_to(artifact_root.resolve()), "direct evidence must stay in its own ignored subtree")
    output = directory if checker_directory is None else Path(checker_directory).resolve()
    require(output.is_relative_to(artifact_root.resolve()), "direct checker output must stay in its own ignored subtree")
    report = json.loads((directory / "probe_report.json").read_text())
    provenance = json.loads((directory / "provenance.json").read_text())
    manifest = json.loads((directory / "artifact_manifest.json").read_text())
    worker_source = report["source"]
    source_binding = bind_direct_checker_source(worker_source, checker_source, direct_profile=report["direct_profile"])
    require(worker_source == checker_source or (checker_directory is not None and output != directory),
        "cross-head direct checker requires an explicit fresh separate checker directory")
    validate_metadata_bindings(report, provenance, manifest, checker_source=checker_source,
                               checker_environment=checker_environment, stage=stage,
                               research_wall_seconds=research_wall_seconds, research_memory_gib=research_memory_gib)
    selected_cap = direct_memory_cap(report.get("direct_profile"), stage, research_wall_seconds, research_memory_gib)
    metadata = reviewed_direct_profile_metadata(report["direct_profile"])
    validate_array_inventory(report, stage)
    saved = SavedRun(directory, manifest, allocation_gate, checker_environment)
    saved.source = worker_source
    # Includes unused controls: a complete finite descriptor declaration alone
    # cannot hide NaN/Inf in an array omitted from later comparisons.
    for name in manifest:
        value = saved.load(name)
        del value
    checks, raw_checks, operator_checks, shared_checks = [], [], [], []

    def add_to(collection):
        def add(name, value, limit, **facts):
            value = float(value); finite_gate(value, limit, name)
            collection.append({"name": name, "measured": value, "limit": float(limit), "passed": True, **facts})
        return add
    add, raw_add = add_to(checks), add_to(raw_checks)
    for key, name in (("provenance_receipt", "provenance.json"), ("artifact_manifest_receipt", "artifact_manifest.json")):
        require(report.get(key) == {"path": name, "sha256": file_sha(directory / name)}, "exact report metadata file receipt differs")
    require(file_sha(directory / "abi_manifest.json") == checker_environment["qualification_manifest_sha256"], "actual ABI manifest differs")
    watched = report["supervisor_receipt"]
    supervision = saved.json(watched)
    validate_direct_supervision(supervision, worker_source, maximum_wall=600 if research_wall_seconds is None
        else provenance["resource_contract"]["worker_phase_wall_seconds"], direct_profile=report["direct_profile"],
        stage=stage, research_wall_seconds=research_wall_seconds, research_memory_gib=research_memory_gib)
    source_contract = load_direct_source_contract(artifact_root, new_source=worker_source,
        new_environment=checker_environment, allocation_gate=allocation_gate, direct_profile=metadata.name)
    require(report.get("direct_source_contract") == provenance.get("direct_source_contract") == source_contract
        and source_contract.get("historical_numerical_arrays_used") is False, "qualified Step0 metadata-only source bridge differs")
    events_path = directory / "probe_events.jsonl"
    events, event_file_receipt = load_direct_events(events_path, allocation_gate)
    phase = {}
    if research_wall_seconds is not None:
        phase = saved.json({"path": "phase.json", "file_sha256": file_sha(directory / "phase.json")})
        validate_research_timing(provenance, supervision, events, phase, research_wall_seconds=research_wall_seconds,
            direct_profile=metadata.name)
    validate_research_memory_resources(provenance, supervision, events, phase, direct_profile=report["direct_profile"],
        stage=stage, research_wall_seconds=research_wall_seconds, research_memory_gib=research_memory_gib)
    validate_direct_event_contract(events, report, stage, research_wall_seconds=research_wall_seconds,
                                  research_memory_gib=research_memory_gib)
    validate_same_live_carrier_chain(events, report)
    add("direct_exact_source_ABI_manifest_profile_and_prefactor_event_binding", 0., 0.)
    base_cfg, _, input_sha = pilot_config(root / "input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat", azimuth_deg=5.)
    cfg = build_direct_profile_config(base_cfg, metadata.name)
    require(input_sha == INPUT_SHA and _jsonable(cfg.as_jsonable()) == report["physical_config"], "fresh physical reviewed config differs from unchanged input")
    physical_modes = outgoing_port_modes_3d(cfg)
    validate_direct_mode_roles(physical_modes, metadata.name)
    operator = report["original_operator_qualification"]
    proof = check_direct_original_cell_contributions(operator, load=saved.load, load_csr=saved.csr,
        allocation_gate=allocation_gate, direct_profile=metadata.name)
    require(proof.get("passed") is True and proof.get("numeric_factor_calls") == 0
        and proof.get("global_whole_Ny_matrix_created") is False, "complete original all-column operator proof required")
    if metadata.name == "Y":
        validate_direct_Y_operator_coverage(proof)
    groups = (("source", proof["sources"]), ("complete_xz_y_orbit", proof["complete_actual_xz_y_orbits"]),
        ("original_local_condensation", proof["local_original_condensation"]),
        ("provider_all2x2", proof["existing_provider_all2x2_full_columns"]))
    for name, records in groups:
        require(records, "operator proof cannot contain vacuous coverage")
        for index, item in enumerate(records):
            operator_checks.append({"name": name+"_"+str(index), "passed": True, "recomputed": item})
    fresh = report["fresh_carrier_qualification"]
    require(fresh.get("resource_authority") == "external min(fresh dynamic cap,"
        + ("1.5GiB" if research_memory_gib is None else str(research_memory_gib)+"GiB") + ")/"
        + str(600 if research_wall_seconds is None else research_wall_seconds)
        + "s/zeroSwap/MPI1/thread1 supervision", "fresh carrier selected resource authority differs")
    require(fresh.get("arrays"), "complete fresh actual mesh/MPC/carrier controls must bind the current manifest")
    for name, descriptor in fresh["arrays"].items():
        require(name in manifest, "fresh carrier descriptor is absent from the current manifest")
        validate_descriptor_metadata(descriptor, manifest[name])
        value = saved.descriptor(descriptor)
        del value
    require(fresh["global_carrier_identity_before"] == fresh["global_carrier_identity_after"]
        and len(fresh["local_carrier_identities"]) == metadata.replication_count, "fresh same-live carrier identities changed")
    for b in range(metadata.replication_count):
        require(operator["local_condensation"][b]["same_live_primary_carrier_identity"] == fresh["local_carrier_identities"][b],
                "original operator carrier differs from independently qualified fresh primary carrier")
    for role, volume in [("direct_global", operator["global_source"]),
            *((f"direct_twist_{b}", operator["local_sources"][b]) for b in range(metadata.replication_count))]:
        geometry, geometry_dofmap, tag_indices, tag_values = (saved.load(role+"_"+name) for name in
            ("geometry_x", "cell_geometry_dofmap", "cell_tag_indices", "cell_tag_values"))
        require(len(geometry_dofmap) == volume["cell_count"] and np.array_equal(tag_indices, np.arange(volume["cell_count"]))
            and len(tag_values) == volume["cell_count"]
            and np.array_equal(saved.load(role+"_independent_storage_rows"), saved.reference(volume["native"]["independent"]))
            and np.array_equal(np.sort(saved.load(role+"_slave_storage_rows")), np.sort(saved.reference(volume["native"]["slaves"]))),
            "actual original operator and fresh carrier native/geometry/tag inventories differ")
        for cell in volume["cells"]:
            index = cell["cell_index"]
            require(cell["tag"] == int(tag_values[index])
                and np.array_equal(saved.reference(cell["native_coordinates"]), geometry[geometry_dofmap[index]]),
                "every original volume cell must use the same fresh carrier geometry/material tags")
        add(role+"_complete_actual_mesh_MPC_volume_carrier_binding", 0., 0.)
    gx, gd, gt = (saved.load("direct_global_"+name) for name in ("geometry_x", "cell_geometry_dofmap", "cell_tag_values"))
    for twist, metric in enumerate(fresh["cell_metric_material_cover"]):
        require(metric.get("complete_actual_cell_count") == metadata.cell_count and metric.get("local_actual_cell_count") == metadata.local_cell_count
            and metric.get("replication_count") == metadata.replication_count and metric.get("metric_tolerance") == 1e-12
            and metric.get("all_material_tags_equal") is True and metric.get("cell_cover_exactly_once") is True,
            "actual complete local/global cell metric/material cover required")
        cover = saved.descriptor(metric["cover"])
        lx, ld, lt = (saved.load(f"direct_twist_{twist}_"+name) for name in ("geometry_x", "cell_geometry_dofmap", "cell_tag_values"))
        require(cover.shape == (metadata.local_cell_count, metadata.replication_count) and cover.dtype.kind in "iu" and np.array_equal(np.sort(cover.ravel()), np.arange(metadata.cell_count)),
                "actual original complete cell cover cannot duplicate or omit a cell")
        maximum = 0.
        for cell in range(metadata.local_cell_count):
            for replica in range(metadata.replication_count):
                old = gx[gd[int(cover[cell, replica])]]
                translated = lx[ld[cell]]+np.asarray([0., replica*cfg.period_y/metadata.replication_count, 0.])
                old = old[np.lexsort((old[:, 2], old[:, 1], old[:, 0]))]
                translated = translated[np.lexsort((translated[:, 2], translated[:, 1], translated[:, 0]))]
                maximum = max(maximum, float(np.max(np.abs(old-translated))))
                require(gt[int(cover[cell, replica])] == lt[cell], "actual local/global material tags differ")
        add(f"twist_{twist}_all{metadata.cell_count}_actual_vertex_translation", maximum, 1e-12)
        finite_gate(metric.get("maximum_actual_vertex_difference"), 1e-12, "reported actual metric")
        add(f"twist_{twist}_actual_vertex_measurement_binding", abs(maximum-metric["maximum_actual_vertex_difference"]), 1e-12)
    global_map = EntityMap(operator["global_source"], saved)
    local_maps = [EntityMap(source, saved) for source in operator["local_sources"]]
    require((global_map.ny, global_map.width) == (metadata.ny, metadata.rows_per_q) and all((item.ny, item.width) == (2, metadata.rows_per_q) for item in local_maps),
            "complete original native entity/q profile differs")
    original_c = saved.csr("original_port_C", (metadata.storage_rows, 532), csc=True)
    original_d = saved.csr("original_port_D", (532, metadata.storage_rows))
    contexts, literal_H, physical_rhs = check_raw_carriers(fresh, saved=saved, global_map=global_map, local_maps=local_maps,
        physical_modes=physical_modes, cfg=cfg, original_c=original_c, original_d=original_d, operator_receipt=operator, add=raw_add)
    require(fresh["global_carrier_identity_after"]["assembly_context_sha256"] == canonical_digest(contexts["full"])
        and fresh["global_carrier_identity_after"]["physical_generator_manifest_sha256"] == PHYSICAL_MANIFEST,
        "fresh global carrier context/physical inventory differs")
    for b in range(metadata.replication_count):
        identity = fresh["local_carrier_identities"][b]
        require(identity["assembly_context_sha256"] == canonical_digest(contexts[f"twist_{b}"])
            and identity["physical_generator_manifest_sha256"] == PHYSICAL_MANIFEST,
            "original operator and qualified local carrier context/physical inventory differs")
    for role, context in contexts.items():
        source_files = validate_context_source_role(role, context, worker_source, direct_profile=metadata.name)
        for name, item in source_files.items():
            paths = [key for key in worker_source["files_sha256"] if Path(key).name == name]
            require(len(paths) == 1 and worker_source["files_sha256"][paths[0]] == item["sha256"], "fresh context differs from exact original worker source")
        raw_add(role+"_actual_source_context_kernel_binding", 0., 0.)
    h = saved.load("port_original_H")
    require(np.all(h > 0) and np.array_equal(h, literal_H[0]), "all532 actual primary and literal H must match")
    from src.solvers.fullspace_dtn_action import _canonical_json_bytes
    from src.solvers.dtn_boundary_phase_gauge import _array_signature
    carrier_rows = saved.load("original_carrier_global_rows")
    ownership = saved.load("original_carrier_ownership_range")
    carrier_slaves = saved.load("original_carrier_slave_rows")
    require(int(carrier_rows) == metadata.storage_rows and np.array_equal(ownership, [0, metadata.storage_rows])
        and np.array_equal(np.sort(carrier_slaves), np.sort(saved.reference(operator["global_source"]["native"]["slaves"]))),
        "original global carrier complete storage/MPC ownership differs")
    numeric = hashlib.sha256()
    numeric.update(_canonical_json_bytes({"schema": "task40extra.live-boundary-carrier-digest.v1",
        "global_rows": int(carrier_rows), "ownership_range": tuple(int(value) for value in ownership),
        "mode_count": 532, "slave_rows": _array_signature(carrier_slaves)}))
    c_data, c_rows, c_ptr = (saved.load("original_port_C_"+key) for key in ("data", "indices", "indptr"))
    d_data, d_rows, d_ptr = (saved.load("original_port_D_"+key) for key in ("data", "indices", "indptr"))
    for index, mode in enumerate(physical_modes):
        cs, ce, ds, de = int(c_ptr[index]), int(c_ptr[index+1]), int(d_ptr[index]), int(d_ptr[index+1])
        require(ce > cs and de > ds, "every complete original C/D functional must remain nonempty")
        numeric.update(_canonical_json_bytes({"index": index,
            "key": (index, mode.side, int(mode.m), int(mode.n), mode.polarization), "H": float(h[index]),
            "coupling_rows": _array_signature(c_rows[cs:ce]), "coupling_values": _array_signature(c_data[cs:ce]),
            "projection_rows": _array_signature(d_rows[ds:de]), "projection_values": _array_signature(d_data[ds:de])}))
    require(numeric.hexdigest() == fresh["global_carrier_identity_before"]["carrier_numeric_sha256"],
            "all saved original C/D/H arrays must reproduce the actual fresh live carrier digest")
    add("all532_original_carrier_numeric_digest", 0., 0.)
    add("original_H_coordinate_scaling", relative(saved.load("port_factor_coordinate_scale")-1/np.sqrt(h), 1/np.sqrt(h)), 1e-12)
    q_labels = saved.load("port_q_labels")
    require(np.array_equal(q_labels, [int(mode.n)%metadata.ny for mode in physical_modes]), "all original n aliases must retain original q labels")
    for b in range(metadata.replication_count):
        require(np.array_equal(saved.load(f"twist_{b}_original_H"), literal_H[b+1]), "local primary/literal normalization differs")
    for item in report["direct_provider_blocks"] + report["reformed_blocks"]:
        matrix = saved.csr(item["csr_prefix"], tuple(item["shape"]))
        require(matrix.nnz == item["nnz"] and sparse_hash(matrix) == item["CSR_sha256"], "complete original-proven block CSR hash differs")
        if item in report["direct_provider_blocks"] and item["p"] != item["q"]:
            diagonal = report["reformed_blocks"][item["global_p"]]
            reference = saved.csr(diagonal["csr_prefix"], diagonal["shape"])
            add(item["csr_prefix"]+"_complete_cross_branch", relative(matrix.data, reference.data), 1e-11)
        else: add(item["csr_prefix"]+"_complete_original_block_binding", 0., 0.)
    evidence = report["shared_transform_equivalence"]
    require(evidence.get("schema") == "task40extra.direct-shared-transform-equivalence.v1", "direct streamed shared evidence schema required")
    shared_checks = check_shared_storage_evidence(evidence, load=saved.load, descriptors=manifest,
        allocation_gate=allocation_gate, native_inventories={"full": "independent_storage_rows",
            **{f"twist_{b}": f"twist_{b}_independent_storage_rows" for b in range(metadata.replication_count)}},
        snapshot_contexts=contexts, direct_profile=metadata.name)
    require(shared_checks and all(item["passed"] for item in shared_checks), "complete shared ownership/equivalence proof cannot be vacuous")
    owner_events = [event for event in events if event.get("event") == "shared_transform_owner_stage"]
    require([event["stage"] for event in owner_events] == [item["stage"] for item in evidence["owner_stages"]], "complete actual owner lifecycle event inventory differs")
    for event, owner in zip(owner_events, evidence["owner_stages"], strict=True):
        require(event.get("receipt_sha256") == digest_json(owner), "actual owner stage digest differs")
        admissions = [item for item in events if item.get("event") == "allocation_admission" and item.get("boundary") == owner["allocation_boundary"]]
        require(len(admissions) == 1 and admissions[0].get("admitted") is True
            and 0 < admissions[0].get("current_tree_rss_bytes", 0) < selected_cap
            and events.index(admissions[0]) < events.index(event), "every owner stage requires its actual prior current-RSS admission")
    frozen = next(item for item in events if item.get("event") == "shared_complete_equivalence_before_any_factor")
    frozen = {key: value for key, value in frozen.items() if key not in ("event", "worker_elapsed_seconds")}
    before = next(i for i, item in enumerate(evidence["owner_stages"]) if item["stage"] == "all_sectors_retained_before_factor")
    expected = {**evidence, "owner_stages": evidence["owner_stages"][:before+1], "owner_artifacts": {
        key: value for owner in evidence["owner_stages"][:before+1] for key, value in owner["owner_artifacts"].items()}}
    require(frozen == expected, "shared equivalence before factor detached from complete saved lifecycle")
    if stage == "solve":
        check_solve(report, saved=saved, global_map=global_map, physical_modes=physical_modes, cfg=cfg,
            original_c=original_c, original_d=original_d, h=h, physical_rhs=physical_rhs, add=add)
    collections = (checks, raw_checks, operator_checks, shared_checks)
    require(all(collection and all(item.get("passed") is True for item in collection) for collection in collections),
            "all independent direct/raw/operator/shared categories require nonempty finite checks")
    return {"schema": CHECKER_SCHEMA, "gate_pass": True, "direct_profile": metadata.name, "stage": stage,
        "source": worker_source, "checker_source": checker_source, "environment": checker_environment,
        "direct_source_contract": source_contract, "source_binding": source_binding,
        "event_file_receipt": event_file_receipt,
        "direct_checks": checks, "direct_check_count": len(checks), "raw_checks": raw_checks, "raw_check_count": len(raw_checks),
        "operator_checks": operator_checks, "operator_check_count": len(operator_checks),
        "shared_checks": shared_checks, "shared_check_count": len(shared_checks),
        "historical_original312_reused_for_new_point": False, "original_check_count": 0,
        "factor_count": 0 if stage == "prefactor" else metadata.ny, "PDE_solved": stage == "solve", "official_results": False,
        "historical_arrays_loaded": False, "numeric_factor_calls": 0, "global_Ny_reference_matrices_created": False,
        "report_sha256": file_sha(directory / "probe_report.json"), "artifact_manifest_sha256": file_sha(directory / "artifact_manifest.json"),
        "qualification": f"fresh {metadata.name} exhaustive carrier/operator/owner prefactor" if stage == "prefactor" else f"fresh {metadata.name} complete full original inverse/FGMRES/residual/recovery/all532 output",
        **({"research_wall_seconds": research_wall_seconds,
            "worker_phase_wall_seconds": provenance["resource_contract"]["worker_phase_wall_seconds"]}
           if research_wall_seconds is not None else {}),
        **({"research_memory_gib": research_memory_gib, "requested_tree_cap_bytes": selected_cap}
           if research_memory_gib is not None else {})}



def residual_representation_binding(new_terms, saved_terms, signs, new_residual, saved_residual):
    """Exact saved formula plus a derived addition/subtraction error envelope.

    Independently evaluated operands have their own unchanged action gates.
    Each k-term residual uses k-1 rounded additions. The difference identity
    additionally uses k operand subtractions, one residual subtraction, a
    k-1 addition sum, and one final subtraction. With u=eps/2, gamma(k-1)
    bounds each sum; the four u terms below cover those subtraction errors.
    This checks representation consistency and grants no equation residual pass.
    """
    import numpy as np
    k = len(signs)
    require(k in (2, 3) and signs[0] == 1 and all(sign in (-1, 1) for sign in signs)
        and len(new_terms) == len(saved_terms) == k, "explicit finite residual expression required")
    shape = np.asarray(new_residual).shape
    arrays = [*new_terms, *saved_terms, new_residual, saved_residual]
    require(len(shape) == 1 and all(np.asarray(a).shape == shape and np.asarray(a).dtype == np.dtype("complex128")
        and np.isfinite(a).all() for a in arrays), "complete finite complex128 residual operands required")
    def replay(terms):
        value = np.asarray(terms[0]).copy()
        for sign, term in zip(signs[1:], terms[1:], strict=True):
            value = value+term if sign == 1 else value-term
        return value
    require(np.array_equal(replay(saved_terms), saved_residual), "saved residual is detached from its exact saved operands")
    require(np.array_equal(replay(new_terms), new_residual), "independent residual is detached from its evaluated operands")
    def norm(a):
        value = float(np.linalg.norm(a))
        require(math.isfinite(value) and value >= 0, "finite residual operation norm required")
        require(value != 0 or not np.any(np.asarray(a) != 0),
                "nonzero residual operand/error norm underflowed to zero")
        return value
    differences = [np.asarray(a)-np.asarray(b) for a, b in zip(new_terms, saved_terms, strict=True)]
    summed = replay(differences)
    residual_difference = np.asarray(new_residual)-np.asarray(saved_residual)
    defect = residual_difference-summed
    operand_norm_sum = sum(norm(a) for a in [*new_terms, *saved_terms])
    difference_norm_sum = sum(norm(a) for a in differences)
    u = np.finfo(float).eps/2
    gamma = (k-1)*u/(1-(k-1)*u)
    # Both residual evaluation sums + operand difference subtractions +
    # residual subtraction + signed difference sum + final defect subtraction.
    roundoff = (gamma*operand_norm_sum + u*operand_norm_sum
        + u*(norm(new_residual)+norm(saved_residual)) + gamma*difference_norm_sum
        + u*(norm(residual_difference)+norm(summed)))
    bound = difference_norm_sum+roundoff
    difference_norm, defect_norm = norm(residual_difference), norm(defect)
    require(math.isfinite(roundoff) and math.isfinite(bound), "finite derived residual difference bound required")
    require(defect_norm <= roundoff and difference_norm <= bound,
            "residual representation difference exceeds operand-error plus derived roundoff bound")
    return {"saved_exact_definition": True, "independent_exact_definition": True,
        "operand_difference_norm_sum": difference_norm_sum, "residual_difference_norm": difference_norm,
        "difference_consistency_defect_norm": defect_norm, "derived_roundoff_bound": roundoff,
        "derived_operand_plus_roundoff_bound": bound, "operation_norm_sum": operand_norm_sum,
        "unit_roundoff": float(u), "sum_gamma": float(gamma), "residual_term_count": k,
        "error_model": "rounded complex128 additions/subtractions; operands independently checked",
        "tiny_residual_relative_precision_claimed": False}


def check_solve(report, *, saved, global_map, physical_modes, cfg, original_c, original_d, h, physical_rhs, add):
    import numpy as np
    from src.solvers.y_orbit_direct_operator_qualification import saved_direct_volume_action
    from src.solvers.dtn_boundary_phase_gauge import (solver_amplitudes_from_global,
        incident_projection_in_solver_coordinates, BOUNDARY_PLANE)
    from src.solvers.y_orbit_centered_evidence import compare_mode_evidence
    metadata = reviewed_direct_profile_metadata(report["direct_profile"])
    independent, slaves = saved.load("independent_storage_rows"), saved.load("full_mpc_slaves")
    interiors = saved.load("actual_interior_positions")
    source = report["original_operator_qualification"]["global_source"]
    require(np.array_equal(independent, saved.reference(source["native"]["independent"]))
        and np.array_equal(np.sort(slaves), np.sort(saved.reference(source["native"]["slaves"])))
        and len(interiors) == metadata.interior_rows and len(np.unique(interiors)) == metadata.interior_rows
        and np.all((interiors >= 0) & (interiors < metadata.independent_rows)), "all actual FE/interior/MPC channels differ")
    interior_storage = saved.load("direct_global_interior_storage_rows")
    require(np.array_equal(np.sort(independent[interiors]), interior_storage), "every actual interior load channel must be audited")
    etas = [complex(*value) for value in report["original_operator_qualification"]["global_eta"]]
    check_notch_source(report, saved=saved, regular=source, add=add)
    add("physical_full_original_literal_RHS", relative(saved.load("physical_rhs")-physical_rhs[independent], physical_rhs[independent]), 1e-10)
    rng = np.random.default_rng(20261001)
    generic = rng.standard_normal(metadata.independent_rows)+1j*rng.standard_normal(metadata.independent_rows)
    require(np.array_equal(saved.load("generic_rhs"), generic), "original direct generic load seed/complete channels differ")
    generic_norms = np.linalg.norm(global_map.modal(generic, dual=True, etas=etas), axis=1)
    require(np.min(generic_norms)/np.linalg.norm(generic_norms) >= 1e-3, "generic load must excite every actual q")
    interior_rhs = np.zeros(metadata.independent_rows, complex)
    j = np.arange(len(interiors)); interior_rhs[interiors] = np.cos(.29*j)+1j*np.sin(.43*j)
    interior_rhs /= np.linalg.norm(interior_rhs)
    require(np.array_equal(saved.load("interior_only_rhs"), interior_rhs), "complete original actual-interior source formula differs")
    changed_native = np.unique(np.concatenate([saved.reference(source["cells"][cell]["native_dofs"]) for cell in report["changed_cells"]]))
    supported = np.flatnonzero(np.isin(independent, changed_native))
    expected_supported = np.zeros(metadata.independent_rows, complex); j = np.arange(len(supported))
    expected_supported[supported] = np.cos(.31*j)+1j*np.sin(.47*j); expected_supported /= np.linalg.norm(expected_supported)
    require(np.array_equal(saved.load("notch_supported_rhs"), expected_supported)
        and report["notch_supported_RHS"] == {"support_actual_changed_cells": report["changed_cells"],
            "support_independent_rows": len(supported), "full_original_FE_load": True, "seed_formula": "cos(.31j)+i sin(.47j)"},
        "complete actual changed-cell original source formula/support differs")
    samples = report["sampled_notch_q_coupling"]
    require([item.get("source_q") for item in samples] == list(range(metadata.ny)), "all actual q original notch coupling diagnostic states required")
    total_norms, off_norms = [], []
    for q in range(metadata.ny):
        j = np.arange(metadata.rows_per_q); modal = np.cos(.37*j)+1j*np.sin(.23*j)
        canonical = np.concatenate([etas[q]**orbit*modal/math.sqrt(metadata.ny) for orbit in range(metadata.ny)])
        sample = global_map.apply(canonical, "primal_from_canonical")
        storage = np.zeros(metadata.storage_rows, complex); storage[independent] = sample
        a0 = saved_direct_volume_action(report["original_operator_qualification"], storage, load=saved.load, allocation_gate=saved.gate)
        a1 = saved_direct_volume_action(report["notch_original_volume_source"], storage, load=saved.load, allocation_gate=saved.gate)
        delta = global_map.modal((a1-a0)[independent], dual=True, etas=etas)
        total_norms.append(float(np.linalg.norm(delta)))
        delta[q] = 0; off_norms.append(float(np.linalg.norm(delta)))
        for metric, value in (("delta_dual_norm", total_norms[-1]), ("off_q_delta_dual_norm", off_norms[-1])):
            recorded = samples[q][metric]; finite_gate(recorded, float("inf"), metric)
            add(f"notch_sample_q_{q}_"+metric, abs(recorded-value)/max(abs(recorded), abs(value), np.finfo(float).tiny), 1e-10)
    coupling = float(np.linalg.norm(off_norms)/np.linalg.norm(total_norms))
    require(coupling >= 1e-8, "actual notch material tensors must genuinely couple original q channels")
    add("notch_original_volume_sampled_coupling_record", abs(coupling-report["sampled_notch_off_q_delta_relative"])/coupling, 1e-10)
    for q in range(metadata.ny):
        matrix = saved.csr(f"q_{q}_S", (metadata.augmented_rows_per_q[q], metadata.augmented_rows_per_q[q]))
        a, b, xa, xb, repeat, total = (saved.load(f"q_{q}_"+key) for key in
            ("rhs_a", "rhs_b", "solution_a", "solution_b", "solution_a_repeat", "solution_sum"))
        require(all(value.dtype == np.dtype("complex128") for value in (a, b, xa, xb, repeat, total))
            and np.linalg.norm(a) > 0 and np.linalg.norm(b) > 0, "nonvacuous original block factor controls required")
        for name, value, rhs in (("a", xa, a), ("b", xb, b), ("sum", total, a+b)):
            add(f"q_{q}_original_factor_residual_"+name, relative(matrix@value-rhs, rhs), 1e-10)
        residual = max(relative(matrix@xa-a, a), relative(matrix@xb-b, b))
        repeated, linear = relative(repeat-xa, xa), relative(total-xa-xb, total)
        add(f"q_{q}_repeat", repeated, 1e-11); add(f"q_{q}_linearity", linear, 1e-11)
        test = report["factor"]["tests"][q]
        for metric, value in (("true_block_residual", residual), ("repeated_difference", repeated), ("linearity_difference", linear)):
            finite_gate(test.get(metric), 1e-10 if metric == "true_block_residual" else 1e-11, "reported factor "+metric)
            add(f"q_{q}_reported_"+metric, abs(value-test[metric])/max(abs(value), abs(test[metric]), np.finfo(float).tiny), 1e-8)
    e, k, outward = (saved.load("original_mode_"+name) for name in ("e_vectors", "k_vectors", "outward_signs"))
    denominator, area = saved.load("original_mode_magnetic_denominator"), saved.load("original_mode_boundary_area")
    incident = np.asarray([incident_projection_in_solver_coordinates(mode, cfg, BOUNDARY_PLANE) for mode in physical_modes])
    require(np.array_equal(e, [mode.e_vector for mode in physical_modes]) and np.array_equal(k, [mode.k_vector for mode in physical_modes])
        and np.array_equal(outward, [1 if mode.side == "top" else -1 for mode in physical_modes])
        and np.array_equal(incident, saved.load("original_mode_incident_projections"))
        and denominator == cfg.k0*complex(cfg.mu_r) and area == cfg.period_x*cfg.period_y,
        "all physically regenerated original modes/incident/normalization differ")
    coefficients, offsets, masters = (saved.load("full_mpc_"+name) for name in ("coefficients", "offsets", "masters"))
    require(offsets[0] == 0 and offsets[-1] == len(coefficients) == len(masters) and np.all(np.diff(offsets) >= 0)
        and len(np.intersect1d(slaves, masters)) == 0 and np.array_equal(np.sort(slaves), np.setdiff1d(np.arange(metadata.storage_rows), independent)),
        "actual finalized full original MPC partition differs")
    d_norms = np.sqrt(np.asarray(original_d.multiply(original_d.conj()).sum(axis=1)).real.ravel())
    q_labels = saved.load("port_q_labels")
    controls = report.get("augmented_controls", [])
    require([item.get("q") for item in controls] == list(range(metadata.ny)), "every q complete manufactured control required")
    packets = [(f"aug_q_{q}", "regular", None, packet) for q, packet in enumerate(controls)]
    packets += [(family+"_"+name, family, name, report[key][name]) for family, key in
        (("regular", "regular_sources"), ("notch", "notched_sources")) for name in SOURCES]
    for label, family, source_name, packet in packets:
        active, field, rhs_storage = (saved.load(label+"_"+key) for key in ("solution", "solution_storage", "rhs_storage"))
        f = saved.load(label+"_FE_rhs") if source_name is None else saved.load(source_name+"_rhs")
        g = saved.load(label+"_port_rhs") if source_name is None else np.zeros(532, complex)
        require(np.array_equal(field[independent], active) and np.all(field[slaves] == 0)
            and np.array_equal(rhs_storage[independent], f) and np.all(rhs_storage[slaves] == 0), "original storage/source/slave-zero binding differs")
        if source_name is None:
            q = packet["q"]; modal = global_map.modal(f, dual=True, etas=etas)
            require(np.count_nonzero(modal[q]) == metadata.rows_per_q and np.count_nonzero(f[interiors]) == metadata.interior_rows
                and np.count_nonzero(g[q_labels == q]) == metadata.q_port_counts[q] and np.all(g[q_labels != q] == 0),
                "complete q FE/interior/nonzero port manufactured loads cannot be vacuous")
            add(label+"_complete_single_q_dual_load", relative(np.delete(modal, q, axis=0), modal[q]), 1e-11)
        elif source_name == "interior_only":
            outside = np.setdiff1d(np.arange(metadata.independent_rows), interiors)
            require(np.count_nonzero(f[interiors]) == metadata.interior_rows and np.all(f[outside] == 0), "all actual cell-interior load channels required")
        volume_source = report["original_operator_qualification"] if family == "regular" else report["notch_original_volume_source"]
        volume = saved_direct_volume_action(volume_source, field, load=saved.load, allocation_gate=saved.gate)
        projection = np.asarray(original_d@field)
        alpha = saved.load(label+"_auxiliary_ports")
        coupling = np.asarray(original_c@alpha)
        action = volume + np.asarray(original_c@(projection/h))
        effective = f - np.asarray(original_c@(g/h))[independent]
        native = effective-action[independent]
        top = f-volume[independent]-coupling[independent]
        port = projection-h*alpha+g
        add(label+"_complete_original_volume_action", relative(volume-saved.load(label+"_volume_action"), volume), 1e-11)
        add(label+"_complete_original_action", relative(action-saved.load(label+"_original_action"), action), 1e-11)
        add(label+"_final_D_field_projection", relative(projection-saved.load(label+"_projection"), projection), 1e-11)
        add(label+"_final_C_alpha_coupling", relative(coupling-saved.load(label+"_coupling_action"), coupling), 1e-11)
        require(np.array_equal(saved.load(label+"_normalization_h"), h), "packet original full H inventory differs")
        operation = d_norms*np.linalg.norm(active)+np.abs(h*alpha)+np.abs(g)
        add(label+"_original_native_true_residual", relative(native, effective), 1e-10)
        add(label+"_augmented_FE_true_residual", relative(top, f), 1e-10)
        add(label+"_all532_augmented_port_closure", operation_error(np.abs(port), operation), 1e-10)
        saved_volume = saved.load(label+"_volume_action")[independent]
        saved_coupling = saved.load(label+"_coupling_action")[independent]
        saved_action = saved.load(label+"_original_action")[independent]
        saved_projection = saved.load(label+"_projection")
        saved_effective = saved.load(label+"_effective_rhs") if source_name is None else f
        saved_native = saved.load(label+"_native_residual")[independent]
        saved_top = saved.load(label+"_augmented_FE_residual")[independent]
        saved_port = saved.load(label+"_augmented_port_residual")
        # The saved formula and both original equation residuals are distinct
        # gates. Cross-representation differences track the accepted operand
        # errors and arithmetic envelope, rather than tiny residual precision.
        for suffix, new_terms, old_terms, signs, new_value, old_value in (
            ("native", (effective, action[independent]), (saved_effective, saved_action), (1, -1), native, saved_native),
            ("augmented_FE", (f, volume[independent], coupling[independent]), (f, saved_volume, saved_coupling), (1, -1, -1), top, saved_top),
            ("augmented_port", (projection, h*alpha, g), (saved_projection, h*alpha, g), (1, -1, 1), port, saved_port)):
            saved.gate("direct_checker_"+label+"_"+suffix+"_residual_representation_binding",
                {"matrix_payload_bytes": 0, "workspace_bytes": (2*len(signs)+8)*new_value.size*16+(4<<20)})
            binding = residual_representation_binding(new_terms, old_terms, signs, new_value, old_value)
            add(label+"_"+suffix+"_saved_operand_definition_and_difference_binding", 0., 0., **binding)
        add(label+"_saved_original_native_true_residual", relative(saved_native, saved_effective), 1e-10)
        add(label+"_saved_augmented_FE_true_residual", relative(saved_top, f), 1e-10)
        add(label+"_saved_all532_augmented_port_closure", operation_error(np.abs(saved_port), operation), 1e-10)
        identity = top-np.asarray(original_c@(port/h))[independent]
        add(label+"_native_equals_augmented_FE_minus_C_Hinv_port", relative(native-identity, np.asarray([np.linalg.norm(effective)+np.linalg.norm(action[independent])])), 1e-10)
        if source_name is None:
            add(label+"_effective_rhs_sign_binding", relative(saved.load(label+"_effective_rhs")-effective, effective), 1e-12)
            add(label+"_all532_port_operation_scale_binding", operation_error(np.abs(saved.load(label+"_port_operation_scale")-operation), operation), 1e-12)
            continue
        add(label+"_A1_final_field_alpha", operation_error(np.abs(alpha-projection/h), d_norms*np.linalg.norm(active)/h), 1e-10)
        recovered = field.copy()
        for slave in slaves:
            start, stop = int(offsets[slave]), int(offsets[slave+1])
            require(stop > start, "actual slave requires complete original MPC expansion")
            recovered[slave] = coefficients[start:stop]@field[masters[start:stop]]
        add(label+"_actual_MPC_field_backsubstitution", relative(saved.load(label+"_recovered_field")-recovered, recovered), 1e-12)
        total = projection/h
        local_incident = incident if source_name == "physical" else np.zeros(532, complex)
        outgoing = total.copy(); outgoing[outward == 1] -= local_incident[outward == 1]
        electric = outgoing[:, None]*e; magnetic = np.cross(k, electric)/denominator
        unit_magnetic = np.cross(k, e)/denominator
        power = np.maximum(.5*np.real(np.cross(electric, np.conj(magnetic)))[:, 2]*outward, 0)*area
        scale = d_norms/h*np.linalg.norm(active)
        expected = {label+"_plane_total_auxiliary": total, label+"_plane_outgoing_auxiliary": outgoing,
            label+"_plane_electric": electric, label+"_plane_magnetic": magnetic,
            label+"_direct_plane_outgoing_power_diagnostic": power, label+"_mode_local_amplitude_scale": scale,
            label+"_plane_electric_scale": scale*np.linalg.norm(e, axis=1),
            label+"_plane_magnetic_scale": scale*np.linalg.norm(unit_magnetic, axis=1),
            label+"_mode_power_operation_scale": .5*area*(scale+np.abs(local_incident))**2*np.linalg.norm(e, axis=1)*np.linalg.norm(unit_magnetic, axis=1)}
        require(np.array_equal(saved.load(label+"_plane_incident_projections"), local_incident), "source original incident subtraction differs")
        for key in ("mode_local_amplitude_scale", "plane_electric_scale", "plane_magnetic_scale", "mode_power_operation_scale"):
            expected_scale = expected[label+"_"+key]
            add(label+"_"+key+"_binding", operation_error(np.abs(saved.load(label+"_"+key)-expected_scale), expected_scale), 1e-12)
        for key, metric in compare_mode_evidence(saved.load, expected.__getitem__, label).items():
            add(label+"_independent_all532_"+key, metric["relative_local_operation_error_max"], 1e-10,
                compared_modes=532, worst_mode_index=metric["worst_mode_index"])
        for key, plane, operation in (("global_total_auxiliary", total, scale), ("global_incident_projections", local_incident, np.abs(local_incident))):
            converted = solver_amplitudes_from_global(saved.load(label+"_"+key), physical_modes, cfg, BOUNDARY_PLANE)
            add(label+"_all532_"+key+"_original_plane_binding", operation_error(np.abs(converted-plane), operation), 1e-10)
        norms = np.linalg.norm(global_map.modal(active, dual=False, etas=etas), axis=1)
        add(label+"_complete_primal_q_norms", relative(norms-packet["solution_primal_q_norms"], norms), 1e-12)
        output = packet.get("outputs", {})
        require(output.get("finite_plane_mode_count") == 532 and output.get("status") == "representable_global_output"
            and output.get("global_output_component_consistency_checked") is True
            and output.get("full_physical_field_recovered") is True and output.get("official_results") is False,
            "complete existing original field and all532 representable outputs required")
        if family == "notch":
            require(packet.get("reason", 0) > 0 and 0 < packet.get("iterations", 0) <= 128
                and packet.get("outer_operator") == "full_original_3D_FFCx_form_action_plus_all_DtN_modes"
                and packet.get("right_pc") == "all_y_blocks_regular_geometry_reference_inverse", "original right-FGMRES positive convergence required")
            history = packet.get("history", [])
            require(len(history) == packet["iterations"]+1 and [entry.get("iteration") for entry in history] == list(range(len(history))),
                    "complete original true residual history required")
            for entry in history: finite_gate(entry.get("full_original_true_residual"), float("inf"), label+"_history")
            if source_name == "physical":
                nonzero = float(np.linalg.norm(norms[1:])/np.linalg.norm(norms))
                require(nonzero > 1e-12, "original notch physical field must retain transverse q channels")
                add(label+"_nonzero_q_record", abs(nonzero-packet["nonzero_q_primal_relative"]), 1e-12)


def check_notch_source(report, *, saved, regular, add):
    """Same full topology/MPC/maps; exact reviewed box-derived material tensors."""
    from src.solvers.y_orbit_direct_operator_qualification import _check_source
    metadata = reviewed_direct_profile_metadata(report["direct_profile"])
    notch = report["notch_original_volume_source"]
    check = _check_source(notch, load=saved.load, gate=saved.gate, metadata=metadata)
    require(check.get("cell_count") == metadata.cell_count and notch.get("role") == "notch"
        and notch.get("explicit_shared_entity_config_for_changed_material") is True,
        "complete independently verified original notch source required")

    def numeric_identity(value):
        if isinstance(value, dict):
            if "artifact" in value:
                return {key: value[key] for key in ("shape", "dtype", "numeric_sha256")}
            return {key: numeric_identity(member) for key, member in value.items()}
        if isinstance(value, list):
            return [numeric_identity(member) for member in value]
        return value

    require(numeric_identity(notch["native"]) == numeric_identity(regular["native"])
        and numeric_identity(notch["entities"]) == numeric_identity(regular["entities"])
        and numeric_identity(notch["interior_positions"]) == numeric_identity(regular["interior_positions"])
        and numeric_identity(notch["trace_positions"]) == numeric_identity(regular["trace_positions"]),
        "notch must preserve every original native/MPC/entity/orientation channel and row map")
    changed_tags, changed_tensors, expected = set(), set(), set()
    for old, new in zip(regular["cells"], notch["cells"], strict=True):
        index = old["cell_index"]
        require(index == new["cell_index"] and all(old[key] == new[key] for key in ("grid", "widths", "cell_info"))
            and all(numeric_identity(old[key]) == numeric_identity(new[key]) for key in
                ("native_dofs", "native_coordinates", "canonical_ids", "canonical_map")),
            "changed material cannot change actual original geometry/dofs/MPC/orientation/maps")
        axes = metadata.global_axes
        grid = old["grid"]
        lower = (25, 25/6, 40) if metadata.name == "Y" else (25, 6.25, 40)
        upper = (33.5, 100/6, 80) if metadata.name == "Y" else (33.5, 18.75, 80)
        if all(lower[d]*(7/135) <= axes[d][grid[d]] and axes[d][grid[d]+1] <= upper[d]*(7/135)
               for d in range(3)):
            expected.add(index)
        if old["tag"] != new["tag"]: changed_tags.add(index)
        if old["oriented_tensor"]["numeric_sha256"] != new["oriented_tensor"]["numeric_sha256"]: changed_tensors.add(index)
        if index not in expected:
            require(numeric_identity(old["raw_tensor"]) == numeric_identity(new["raw_tensor"])
                and numeric_identity(old["complete_canonical_contribution"]) == numeric_identity(new["complete_canonical_contribution"]),
                "unchanged cells must retain their entire original300-column tensor/contribution")
        else:
            tags = report["physical_config"]["tags"]
            require(old["tag"] == tags["grating"] and new["tag"] == tags["air"],
                    "approved physical notch must replace exactly grating material with air")
    require(len(expected) == (3 if metadata.name == "Y" else 2)
        and expected == changed_tags == changed_tensors == set(report["changed_cells"]),
            "actual physical-box cells must be exactly the reviewed changed material tags and complete tensors")
    cfg = report["notch_config"]
    box = [value*(7/135) for value in ((25, 33.5, 25/6, 100/6, 40, 80)
        if metadata.name == "Y" else (25, 33.5, 6.25, 18.75, 40, 80))]
    require(cfg.get("air_void_box_nm") == box, "notch physical geometry differs from approved reviewed profile box")
    regular_cfg = report["physical_config"]
    require({key: value for key, value in cfg.items() if key not in ("case_name", "geometry_identity", "air_void_box_nm")}
        == {key: value for key, value in regular_cfg.items() if key not in ("case_name", "geometry_identity", "air_void_box_nm")},
        "notch changed an unapproved physical/config/source field")
    add("notch_complete_original_source_and_exact_three_tensor_support" if metadata.name == "Y"
        else "notch_complete_original_source_and_exact_two_tensor_support", 0., 0.)
