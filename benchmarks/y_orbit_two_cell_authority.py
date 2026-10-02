"""Immutable full-p4 validation authority for the Q0--Q2 quotient audit.

This module cannot build a candidate, create a factor, or solve. Historical
full maps are exposed solely for validation; the candidate must build local
maps and action-only condensation without depending on these saved full maps.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


AUTHORITY_HEAD = "ad356715da86ab34fa6b10838cccc8629b3f6e8b"
AUTHORITY_RUN = "y_orbit_sparse_p4_phi5_centered_attempt1"
AUTHORITY_HASHES = {
    "probe_report.json": "a71c0e177394b436c9b787b62f780db19ebcdce0410a85a346dbcf4fcc42151f",
    "independent_checker.json": "bdc161047c8b6ececfa9c0086beedd66c8abc510049ba0b664df887fa848c56a",
    "provenance.json": "2a6d5915429dda8294b0ec5be59dbf04f0ff5ca322d35007a0c52efe9fb44d1f",
    "summary.json": "9978498da5a2391c0df81922f72b99aee3364d44eb6c23d1437d87d67048481f",
    "live_component_receipt.json": "95701a0adde26f5c190be0357614df287f487d5ae6f49d6e6d5668ea845ea4fd",
    "abi_manifest.json": "007a5f794c3b1f4f7431917f15700cd1cfef5606f3601b07c429135ec5270e96",
}
Q_HASHES = (
    "9b4973d558865531bd6c64f973cdf7b5c72360564eace0fb6dbf32e122223755",
    "65117a867af8cb1b678a6435f87053581a931db2c2bf6716ca53d9a9f0f33d12",
    "9c4905a379341f021d8c2e82817b6523a4261d18e835cb9c6510d2b0643900c8",
    "28d66701a29ba83b2fa9b392d1da90ea88568742162dabde9106c7f2ea0047bc",
)
Q_ROWS = (1884, 1960, 1960, 1960)
Q_NNZ = (436012, 454744, 454744, 455143)
PHYSICAL_MANIFEST = "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951"
TREE_CAP_BYTES = 3 * 1024**3 // 2


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def bound_path(directory, relative):
    path = (Path(directory) / relative).resolve()
    if not path.is_relative_to(Path(directory).resolve()) or not path.is_file():
        raise ValueError("artifact must be an existing file within its run directory")
    return path


def dependency_diff(old_source, new_source):
    """Record all paths, including additions/deletions, without source equality."""
    if (old_source.get("head") != AUTHORITY_HEAD or old_source.get("dirty")
            or new_source.get("dirty") or new_source.get("head") == AUTHORITY_HEAD
            or old_source.get("branch") != "task40extra_dot_parallel_cloud"
            or new_source.get("branch") != old_source.get("branch")):
        raise ValueError("requires immutable old ad356715 and distinct clean own-branch candidate")
    old, new = old_source["files_sha256"], new_source["files_sha256"]
    if not old or not new:
        raise ValueError("complete old/new dependency inventories are required")
    records = [{"path": name, "old_sha256": old.get(name), "new_sha256": new.get(name),
                "relation": ("unchanged" if old.get(name) == new.get(name) else
                             "added" if name not in old else
                             "deleted" if name not in new else "changed")}
               for name in sorted(set(old) | set(new))]
    return {"old_head": AUTHORITY_HEAD, "new_head": new_source["head"],
            "old_manifest_sha256": digest_json(old), "new_manifest_sha256": digest_json(new),
            "all_dependencies": records, "changed_paths": [r["path"] for r in records
                                                           if r["relation"] != "unchanged"],
            "source_equality_claimed": False,
            "qualification": "explicit old validation authority to new candidate bridge"}


def validate_supervision(summary, source, *, maximum_wall=600):
    launch = summary.get("launch_envelope", {})
    delta = summary.get("global_swap_activity", {}).get("delta", {})
    if (summary.get("classification") != "COMPLETED" or summary.get("leader_exit_code") != 0
            or summary.get("source_state") != source
            or summary.get("sampled_process_tree_swap_peak_bytes") != 0
            or summary.get("descendants_cleared") is not True
            or summary.get("process_tree_all_status_readable") is not True
            or summary.get("process_tree_all_identity_complete") is not True
            or not 0 < summary.get("sampled_process_tree_rss_peak_bytes", 0) < TREE_CAP_BYTES
            or not 0 < summary.get("elapsed_seconds", 0) < maximum_wall
            or not 0 < launch.get("launch_cap_bytes", 0) <= TREE_CAP_BYTES
            or delta.get("pswpin_pages") != 0 or delta.get("pswpout_pages") != 0):
        raise ValueError("supervised source/whole-tree/zero-global-swap/time identity failed")
    return True


def validate_old_metadata(report, checker, provenance, *, new_source, new_environment):
    source = report.get("source", {})
    if (source.get("head") != AUTHORITY_HEAD or source.get("dirty")
            or report.get("source_clean_unchanged") is not True
            or provenance.get("source") != source or checker.get("source") != source
            or checker.get("checker_source") != source
            or report.get("status") != "SPARSE_CONDENSED_FULL3D_PROBE_PASS"
            or checker.get("gate_pass") is not True or checker.get("evidence_valid") is not True
            or report.get("degree") != 4 or checker.get("degree") != 4
            or report.get("dtn_phase_gauge") != "boundary_plane"
            or report.get("auxiliary_gauge") != "positive-h"
            or checker.get("auxiliary_gauge") != "positive-h"
            or report.get("live_component_oracle") is not True
            or checker.get("live_component_oracle") is not True
            or checker.get("p4_original_functionals_bound_to_live_carrier") is not True
            or report.get("environment") != provenance.get("environment")
            or report.get("environment") != new_environment
            or checker.get("report_sha256") != AUTHORITY_HASHES["probe_report.json"]
            or checker.get("provenance_sha256") != AUTHORITY_HASHES["provenance.json"]
            or checker.get("artifact_manifest_sha256") != digest_json(report.get("artifacts"))):
        raise ValueError("immutable old p4 report/checker/source/ABI/degree identity failed")
    checks = checker.get("checks", [])
    if len(checks) != 148 or any(v.get("passed") is not True
                               or not math.isfinite(v.get("measured", math.nan))
                               or v["measured"] > v["limit"] for v in checks):
        raise ValueError("old independent checker complete measured gates failed")
    layout = report.get("layout", {})
    trace = report.get("coordinates", {}).get("trace", {})
    identity = report.get("centered_identity", {})
    if (layout.get("independent_rows") != 15872 or layout.get("full_storage_rows") != 17204
            or layout.get("ny") != 4 or layout.get("all_q") != [0, 1, 2, 3]
            or trace.get("complete_trace_rows") != 7232
            or trace.get("complete_interior_rows") != 8640
            or identity.get("physical_generator_manifest_sha256") != PHYSICAL_MANIFEST
            or len(report.get("mode_keys", [])) != 532
            or len({tuple(k) for k in report["mode_keys"]}) != 532):
        raise ValueError("old full p4 FE/trace/interior/global-mode inventory failed")
    blocks = report.get("reference_factor", {}).get("input_blocks", [])
    if len(blocks) != 4 or [v.get("q") for v in blocks] != list(range(4)):
        raise ValueError("old authority must contain all four ordered q blocks")
    required = {f"q_{q}_S_{part}" for q in range(4) for part in ("data", "indices", "indptr")}
    required |= {f"{prefix}_{part}" for prefix in ("full_Q", "full_R_inverse", "full_F",
                 "trace_R_t", "trace_R_t_inverse", "trace_F_t", "original_port_C", "original_port_D")
                 for part in ("data", "indices", "indptr")}
    required |= {"independent_storage_rows", "port_original_H", "port_q_labels", "port_eta",
                 "trace_full_independent_trace_positions", "trace_full_canonical_trace_positions",
                 "original_mode_e_vectors", "original_mode_k_vectors", "original_mode_outward_signs",
                 "original_mode_magnetic_denominator", "original_mode_boundary_area",
                 "original_mode_incident_projections"}
    if not required.issubset(report["artifacts"]):
        raise ValueError("old authority required array inventory incomplete")
    for q, block in enumerate(blocks):
        if (block.get("shape") != [Q_ROWS[q], Q_ROWS[q]] or block.get("nnz") != Q_NNZ[q]
                or block.get("CSR_sha256") != Q_HASHES[q]):
            raise ValueError("old authority q identity differs")
    return dependency_diff(source, new_source)


class SavedFullP4Authority:
    """Hash-verified mmap/CSR access to a fixed validation-only old authority."""
    def __init__(self, directory, *, new_source, new_environment, allocation_gate=None):
        self.directory = Path(directory).resolve()
        if self.directory.name != AUTHORITY_RUN:
            raise ValueError("arbitrary stale authority directories are forbidden")
        self.allocation_gate = allocation_gate
        for name, digest in AUTHORITY_HASHES.items():
            if file_sha(bound_path(self.directory, name)) != digest:
                raise ValueError("immutable old authority file hash differs: " + name)
        self.report = json.loads((self.directory / "probe_report.json").read_text())
        checker = json.loads((self.directory / "independent_checker.json").read_text())
        provenance = json.loads((self.directory / "provenance.json").read_text())
        difference = validate_old_metadata(self.report, checker, provenance,
                                          new_source=new_source, new_environment=new_environment)
        summary = json.loads((self.directory / "summary.json").read_text())
        validate_supervision(summary, self.report["source"])
        watched = checker["checker_watchdog_receipt"]
        watch_path = bound_path(self.directory, watched["path"])
        if file_sha(watch_path) != watched["sha256"]:
            raise ValueError("immutable old checker watchdog hash differs")
        validate_supervision(json.loads(watch_path.read_text()), self.report["source"])
        # Reuse the existing strict literal-oracle reader; it never assembles.
        from src.solvers.y_orbit_live_boundary_contract import load_bound_live_receipt
        load_bound_live_receipt(self.directory, self.report["centered_identity"],
                               worker_source=self.report["source"], expected_degree=4)
        # Verify even unused descriptor files before exposing any numerical array.
        for name, descriptor in self.report["artifacts"].items():
            if file_sha(bound_path(self.directory, descriptor["path"])) != descriptor["file_sha256"]:
                raise ValueError("immutable old authority artifact differs: " + name)
        self.receipt = {"run": AUTHORITY_RUN, "hashes": dict(AUTHORITY_HASHES),
                        "source_head": AUTHORITY_HEAD,
                        "artifact_manifest_sha256": digest_json(self.report["artifacts"]),
                        "checker_watchdog_receipt": watched,
                        "qualification_manifest_sha256": new_environment["qualification_manifest_sha256"],
                        "old_new_dependency_diff": difference,
                        "validation_only_full_maps": True, "candidate_setup_uses_old_full_maps": False,
                        "qualification": "Q0-Q2 operator audit only; factors and solve forbidden"}

    def load(self, name):
        import numpy as np
        if not callable(self.allocation_gate):
            raise ValueError("authority array access requires a measured whole-tree allocation gate")
        descriptor = self.report["artifacts"][name]
        path = bound_path(self.directory, descriptor["path"])
        if file_sha(path) != descriptor["file_sha256"]:
            raise ValueError("authority array changed after metadata validation: " + name)
        self.allocation_gate("authority_validation_mmap_" + name,
                             {"matrix_payload_bytes": int(descriptor["payload_bytes"]),
                              "workspace_bytes": 1 << 20, "validation_only": True})
        value = np.load(path, allow_pickle=False, mmap_mode="r")
        if (list(value.shape) != descriptor["shape"] or str(value.dtype) != descriptor["dtype"]
                or value.nbytes != descriptor["payload_bytes"] or value.dtype.hasobject
                or value.flags.writeable):
            raise ValueError("authority shape/dtype/payload/read-only descriptor differs: " + name)
        if value.dtype.kind in "fc":
            flat = value.ravel(order="K")
            for start in range(0, flat.size, 65536):
                if not np.isfinite(flat[start:start + 65536]).all():
                    raise ValueError("nonfinite authority array: " + name)
        return value

    def q_block(self, q):
        if type(q) is not int or q not in range(4):
            raise ValueError("one of the four literal q indices is required")
        from scipy import sparse
        from src.solvers.y_orbit_sparse_reference import sparse_hash, csr_audit
        block = sparse.csr_matrix((self.load(f"q_{q}_S_data"), self.load(f"q_{q}_S_indices"),
                                   self.load(f"q_{q}_S_indptr")), shape=(Q_ROWS[q], Q_ROWS[q]), copy=False)
        csr_audit(block, petsc_index_dtype=self.report["environment"]["petsc_int_type"])
        if block.nnz != Q_NNZ[q] or sparse_hash(block) != Q_HASHES[q]:
            raise ValueError("immutable old q CSR content identity differs")
        return block
