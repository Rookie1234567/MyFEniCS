"""Thin supervised entrypoint for sparse-p2 authority bridge / same-mesh p4.

The existing dense-p2 runner cannot assemble/recover exact condensed systems
or enforce the per-q sparse factor admission policy. Numerical code is in src.
Without --run this prints a plan; external staging is never a runnable source
authority. Integration, clean source commit, tests and parent admission precede
any actual launch.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import traceback

from benchmarks.run_real_p4_probe import environment_facts, source_facts
from src.solvers.real_p4_probe import file_sha256, write_json

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "benchmarks/artifacts/task40extra_dot_parallel_cloud"
INPUT = ROOT / "input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat"
INPUT_SHA = "6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e"
TREE_CAP_BYTES = 3 * 1024**3 // 2
RESERVE_BYTES = 128 * 1024**2
WALL_SECONDS = 600
EXPECTED_RAW_REFERENCE_SCOPE = "same frozen upstream-clipped FE operator; no lost functional restored"
ORACLE_NAME = "y_orbit_p2_phi5_attempt1"
ORACLE_HASHES = {
    "pilot_report.json": "24c05218a32cec8000923564f56209a747f13786a3144b96d2bf982953c7d28f",
    "provenance.json": "42dbdc1471161cf785b0a13556c617d98a27386eb58d04a4ed058e9881295911",
    "independent_checker.json": "e6374883b3cc16a0f72d7146d2ea1cfa289c51df07612184c07465b0881a08c2",
    "summary.json": "9fdb3d3180d20d74038cd3b04c7f8447677f673cd81d07b57b2387cf63c209b8",
}


class SavedDenseP2Authority:
    """Read-only hash-bound existing artifact, never a newly built dense factor."""
    def __init__(self, environment):
        self.directory = ARTIFACT_ROOT / ORACLE_NAME
        for name, digest in ORACLE_HASHES.items():
            if file_sha256(self.directory / name) != digest:
                raise RuntimeError("saved p2 authority receipt hash mismatch: " + name)
        self.report = json.loads((self.directory / "pilot_report.json").read_text())
        provenance = json.loads((self.directory / "provenance.json").read_text())
        checker = json.loads((self.directory / "independent_checker.json").read_text())
        summary = json.loads((self.directory / "summary.json").read_text())
        if (self.report["status"] != "ARCHITECTURE_IDENTITY_AND_NOTCH_PASS"
                or checker.get("gate_pass") is not True or summary["classification"] != "COMPLETED"
                or provenance["source"]["head"] != "ac1410ca1187352fbe398325c5f7aaa33bf0d0bd"
                or self.report["azimuth_deg"] != 5.0
                or provenance["environment"]["qualification_manifest_sha256"]
                != environment["qualification_manifest_sha256"]):
            raise RuntimeError("saved p2 authority source/environment/pass identity is incomplete")
        self.receipt = {"run": ORACLE_NAME, "hashes": ORACLE_HASHES,
                        "source_head": provenance["source"]["head"],
                        "qualification_manifest_sha256": environment["qualification_manifest_sha256"]}

    def load(self, name):
        import numpy as np
        descriptor = self.report["artifacts"][name]
        path = (self.directory / descriptor["path"]).resolve()
        if not path.is_relative_to(self.directory.resolve()) or file_sha256(path) != descriptor["file_sha256"]:
            raise RuntimeError("saved dense p2 artifact hash/path mismatch: " + name)
        value = np.load(path, allow_pickle=False, mmap_mode="r")
        if list(value.shape) != descriptor["shape"] or str(value.dtype) != descriptor["dtype"]:
            raise RuntimeError("saved dense p2 descriptor mismatch: " + name)
        return value

    def require_fixture(self, input_sha, axes, layout, base, generic_rhs):
        import numpy as np
        actual_keys = [(str(e.mode_identity["side"]), int(e.mode_identity["m"]),
                        int(e.mode_identity["n"]), str(e.mode_identity["polarization"]))
                       for e in base["dtn_action"].carrier.entries]
        historical = sorted((e for group in self.report["ports"]["alias_groups"].values() for e in group),
                            key=lambda e: e["index"])
        historical_keys = [(str(e["side"]), int(e["m"]), int(e["n"]), str(e["polarization"]))
                           for e in historical]
        if (input_sha != self.report["input_sha256"] or actual_keys != historical_keys
                or {k: list(v) for k, v in axes.items()} != self.report["axes_nm"]
                or not np.array_equal(layout.independent, self.load("independent_storage_rows"))
                or not np.array_equal(generic_rhs, self.load("generic_rhs"))):
            raise RuntimeError("saved p2 full geometry/native-row/RHS/ordered-port identity differs")
        # Physical FE matrices are compared across ALL columns later, so a new
        # inverse source SHA is allowed. No historical ABI equivalence is inferred.


class SavedCenteredDenseP2Authority(SavedDenseP2Authority):
    """Fresh same-source centered authority with exact checker/representation binding."""
    def __init__(self, path, digest, source, environment):
        from src.solvers.y_orbit_centered_evidence import (
            COMPONENT_IDENTITY, SOURCES, digest_json, require_centered_dense_inventory,
        )
        path = Path(path).resolve()
        if not path.is_relative_to(ARTIFACT_ROOT.resolve()) or file_sha256(path) != digest:
            raise RuntimeError("centered authority report path/hash differs")
        self.directory = path.parent
        self.report = json.loads(path.read_text())
        require_centered_dense_inventory(self.report)
        provenance_path = self.directory/"provenance.json"
        checker_path = self.directory/"independent_checker.json"
        provenance, checker = json.loads(provenance_path.read_text()), json.loads(checker_path.read_text())
        summary = json.loads((self.directory/"summary.json").read_text())
        if (self.report.get("status") != "CENTERED_DENSE_AUTHORITY_PASS"
                or self.report.get("dtn_phase_gauge") != "boundary_plane" or self.report.get("degree") != 2
                or self.report.get("source_clean_unchanged") is not True or self.report.get("source") != source
                or provenance["source"] != source or self.report.get("environment") != environment
                or provenance["environment"] != environment or summary.get("classification") != "COMPLETED"
                or self.report.get("source_names") != list(SOURCES)
                or checker.get("gate_pass") is not True or checker.get("evidence_valid") is not True
                or checker.get("report_sha256") != digest or checker.get("provenance_sha256") != file_sha256(provenance_path)
                or checker.get("artifact_manifest_sha256") != digest_json(self.report["artifacts"])
                or checker.get("source") != source or checker.get("environment") != environment
                or checker.get("identity") != self.report.get("identity") or checker.get("degree") != 2
                or any(self.report["identity"].get(k) != v for k,v in COMPONENT_IDENTITY.items())):
            raise RuntimeError("fresh centered authority/checker/source/gauge identity has not passed")
        watched = checker.get("checker_watchdog_receipt", {})
        wp = (self.directory/watched.get("path", "")).resolve()
        if not wp.is_relative_to(self.directory) or not wp.is_file() or file_sha256(wp) != watched.get("sha256"):
            raise RuntimeError("centered independent checker supervision identity differs")
        ws = json.loads(wp.read_text())
        for receipt in (summary, ws):
            if (receipt.get("classification") != "COMPLETED" or receipt.get("source_state") != source
                    or receipt.get("sampled_process_tree_swap_peak_bytes") != 0
                    or receipt.get("descendants_cleared") is not True or receipt.get("process_tree_all_identity_complete") is not True
                    or receipt.get("process_tree_all_status_readable") is not True
                    or not 0 < receipt["sampled_process_tree_rss_peak_bytes"] < TREE_CAP_BYTES):
                raise RuntimeError("fresh centered dense/checker whole-tree resource authority fails")
        self.receipt = {"report_path": str(path.relative_to(ROOT)), "report_sha256": digest,
            "provenance_sha256": file_sha256(provenance_path), "checker_sha256": file_sha256(checker_path),
            "artifact_manifest_sha256": digest_json(self.report["artifacts"]), "source_head":source["head"],
            "identity": self.report["identity"], "dtn_phase_gauge": "boundary_plane", "qualification": "small_p2_only"}

    def require_fixture(self, input_sha, axes, layout, base, generic_rhs):
        from src.solvers.y_orbit_centered_evidence import centered_identity
        super().require_fixture(input_sha, axes, layout, base, generic_rhs)
        if centered_identity(base) != self.report["identity"]:
            raise RuntimeError("centered actual rebuilt discrete/physical context differs from authority")


def _validate_bridge(path, digest, expected_head, source):
    if not path.is_relative_to(ARTIFACT_ROOT.resolve()) or file_sha256(path) != digest:
        raise RuntimeError("sparse-p2 bridge receipt path/hash mismatch")
    report = json.loads(path.read_text())
    checker_path = path.parent / "independent_checker.json"
    if not checker_path.is_file():
        raise RuntimeError("sparse-p2 bridge needs its independent checker")
    checker = json.loads(checker_path.read_text())
    provenance_path = path.parent / "provenance.json"
    artifact_identity = hashlib.sha256(json.dumps(report["artifacts"], sort_keys=True,
                                               separators=(",", ":")).encode()).hexdigest()
    if (report.get("status") != "SPARSE_CONDENSED_FULL3D_PROBE_PASS" or report["degree"] != 2
            or report.get("source_clean_unchanged") is not True
            or report["source"]["head"] != expected_head
            or report["source"] != source
            or report["saved_dense_p2_bridge"]["passed"] is not True
            or checker.get("gate_pass") is not True or checker.get("evidence_valid") is not True
            or checker.get("report_sha256") != digest
            or checker.get("provenance_sha256") != file_sha256(provenance_path)
            or checker.get("artifact_manifest_sha256") != artifact_identity
            or checker.get("source") != source or checker.get("degree") != 2
            or report.get("auxiliary_gauge") != "raw" or checker.get("auxiliary_gauge") != "raw"
            or report.get("reference_scope") != EXPECTED_RAW_REFERENCE_SCOPE
            or checker.get("representation") != report.get("reference_scope")):
        raise RuntimeError("same-source sparse-p2 qualification bridge has not passed")
    watchdog = checker.get("checker_watchdog_receipt")
    if not isinstance(watchdog, dict):
        raise RuntimeError("sparse-p2 independent checker requires its own supervised receipt")
    watchdog_path = (path.parent / watchdog["path"]).resolve()
    if not watchdog_path.is_relative_to(path.parent) or file_sha256(watchdog_path) != watchdog["sha256"]:
        raise RuntimeError("checker supervised receipt path/hash/classification differs")
    watched = json.loads(watchdog_path.read_text())
    if (watched.get("classification") != "COMPLETED" or watched.get("source_state") != source
            or watched.get("sampled_process_tree_swap_peak_bytes") != 0
            or watched.get("process_tree_all_status_readable") is not True
            or watched.get("process_tree_all_identity_complete") is not True
            or watched.get("descendants_cleared") is not True):
        raise RuntimeError("checker supervised receipt source/resource gates differ")
    return {"report_path": str(path.relative_to(ROOT)), "report_sha256": digest,
            "checker_sha256": file_sha256(checker_path), "source_head": expected_head,
            "not_target_scale_qualification": True}


def _worker(args):
    import numpy as np
    from time import perf_counter
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    from src.solvers.y_orbit_sparse_probe import run_sparse_probe
    from src.solvers.y_orbit_sparse_reference import integer_admission
    from petsc4py import PETSc

    parent = int(os.environ.get("PHYSICAL_WATCHDOG_PARENT_PID", "0"))
    cap = int(os.environ.get("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES", "0"))
    if parent <= 0 or parent != os.getppid() or not 0 < cap <= TREE_CAP_BYTES:
        raise RuntimeError("worker requires its coordinated 1.5GiB whole-tree watchdog")
    source = source_facts(args.expected_head)
    environment = environment_facts()
    component_reuse = None
    if args.dtn_phase_gauge == "boundary_plane":
        from src.solvers.y_orbit_centered_evidence import verify_component_sources
        component_reuse = verify_component_sources(ROOT)
        oracle = SavedCenteredDenseP2Authority(args.dense_authority, args.dense_authority_report_sha256, source, environment)
    else:
        oracle = SavedDenseP2Authority(environment) if args.degree == 2 else None
    bridge = (_validate_bridge(args.bridge_report, args.bridge_report_sha256, args.expected_head, source)
              if args.degree == 4 else None)
    events = args.run_directory / "probe_events.jsonl"
    arrays = args.run_directory / "arrays"
    arrays.mkdir()
    descriptors = {}
    factor_diagnostics = {}
    started = perf_counter()

    def event(name, facts):
        payload = {"event": name, "worker_elapsed_seconds": perf_counter() - started, **facts}
        with events.open("a") as stream:
            stream.write(json.dumps(payload, allow_nan=False) + "\n")
        print(json.dumps(payload, allow_nan=False), flush=True)

    def save_array(name, values):
        values = np.asarray(values)
        if values.dtype.hasobject or (values.dtype.kind in "fc" and not np.isfinite(values).all()):
            raise ValueError("invalid diagnostic artifact")
        path = arrays / (name + ".npy")
        np.save(path, values, allow_pickle=False)
        descriptors[name] = {"path": str(path.relative_to(args.run_directory)), "shape": list(values.shape),
                             "dtype": str(values.dtype), "payload_bytes": int(values.nbytes),
                             "file_sha256": file_sha256(path)}

    def save_factor_diagnostic(name, values):
        """Bounded raw failure evidence, honestly retaining NaN/Inf if present."""
        values = np.asarray(values, dtype=np.complex128)
        if (values.ndim != 1 or values.size > 65536
                or not name.replace("_", "").isalnum()):
            raise ValueError("factor diagnostic exceeds its reviewed vector/name bound")
        raw = args.run_directory / "raw_factor_diagnostics"
        raw.mkdir(exist_ok=True)
        path = raw / (name + ".npy")
        np.save(path, values, allow_pickle=False)
        finite = np.isfinite(values)
        magnitudes = np.abs(values[finite])
        finite_magnitudes = magnitudes[np.isfinite(magnitudes)]
        facts = {"path": str(path.relative_to(args.run_directory)), "shape": list(values.shape),
                 "dtype": str(values.dtype), "file_sha256": file_sha256(path),
                 "finite_entries": int(np.count_nonzero(finite)),
                 "nonfinite_entries": int(values.size - np.count_nonzero(finite)),
                 "finite_abs_max": float(np.max(finite_magnitudes)) if finite_magnitudes.size else None,
                 "raw_failure_diagnostic_only": True, "counts_are_not_solver_pass": True}
        factor_diagnostics[name] = facts
        event("raw_factor_vector_saved", {"name": name, **facts})

    def allocation_gate(name, facts):
        # Admit native CSR dimensions/NNZ before inherited PETSc allocation.
        if name == "condensed_matrix":
            integer_admission((int(facts["rows"]), int(facts["rows"])), int(facts["nnz"]),
                              index_dtype=PETSc.IntType)
        sample = process_tree_snapshot(parent, name, None, pss_sampling_policy="disabled_by_profile")
        if (sample.get("all_status_readable") is not True
                or sample.get("identity_complete") is not True or sample.get("swap_bytes") != 0):
            raise RuntimeError("fresh readable identity/status zero-swap aggregate tree is required")
        payload = int(facts.get("matrix_payload_bytes", facts.get("retained_numeric_bytes_upper", 0)))
        workspace = int(facts.get("workspace_bytes", 0))
        if min(payload, workspace) < 0:
            raise ValueError("negative allocation policy")
        reserve = max(RESERVE_BYTES, int(facts.get("evidence_reserve_bytes", 0)))
        projected = int(sample["rss_bytes"]) + payload + workspace + reserve
        event("allocation_admission", {"boundary": name, "current_tree_rss_bytes": sample["rss_bytes"],
              "additional_payload_bytes": payload, "declared_workspace_bytes": workspace,
              "reserve_bytes": reserve, "projected_tree_bytes": projected, "tree_cap_bytes": cap,
              "facts": facts, "admitted": projected < cap})
        if projected >= cap:
            raise MemoryError("declared additional working set exceeds measured tree policy")

    provenance = {"source": source, "environment": environment, "command": sys.argv,
                  "input_sha256": INPUT_SHA, "degree": args.degree,
                  "auxiliary_gauge": args.auxiliary_gauge,
                  "dtn_phase_gauge": args.dtn_phase_gauge, "component_reuse": component_reuse,
                  "saved_dense_p2_authority": oracle.receipt if oracle is not None else None,
                  "sparse_p2_bridge_receipt": bridge,
                  "resource_contract": {"tree_cap_bytes": cap, "wall_seconds": WALL_SECONDS,
                      "swap_bytes": 0, "mpi": 1, "math_threads": 1,
                      "declared_factor_workspace_allowance_bytes": 512 * 1024**2,
                      "evidence_reserve_bytes": RESERVE_BYTES, "unknown_fill": True,
                      "performance_or_target_capacity_claim": False}}
    write_json(args.run_directory / "provenance.json", provenance)
    shutil.copyfile(environment["qualification_manifest"], args.run_directory / "abi_manifest.json")
    report = {"schema": "task40extra.y-orbit-sparse-condensed-reference.v1", "status": "STARTED"}
    try:
        report = run_sparse_probe(INPUT, degree=args.degree, event=event, save_array=save_array,
                                  allocation_gate=allocation_gate, saved_oracle=oracle,
                                  auxiliary_gauge=args.auxiliary_gauge,
                                  dtn_phase_gauge=args.dtn_phase_gauge,
                                  save_factor_diagnostic=save_factor_diagnostic)
        if source_facts(args.expected_head) != source:
            raise RuntimeError("source identity changed during the sparse probe")
        report.update(source=source, environment=environment, source_clean_unchanged=True,
                      worker_elapsed_seconds=perf_counter() - started, artifacts=descriptors,
                      factor_raw_diagnostics=factor_diagnostics,
                      sparse_p2_bridge_receipt=bridge)
        write_json(args.run_directory / "probe_report.json", report)
        event("probe_complete", {"status": report["status"], "degree": args.degree})
        return 0
    except Exception as exc:
        report.update(status="FAILED", degree=args.degree, error_type=type(exc).__name__, error=str(exc),
                      source=source, artifacts=descriptors, factor_raw_diagnostics=factor_diagnostics,
                      auxiliary_gauge=args.auxiliary_gauge, worker_elapsed_seconds=perf_counter() - started)
        write_json(args.run_directory / "probe_report.json", report)
        (args.run_directory / "probe_traceback.txt").write_text(traceback.format_exc())
        event("probe_failure", {"error_type": type(exc).__name__, "error": str(exc)})
        return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--degree", type=int, choices=(2, 4), default=2)
    parser.add_argument("--auxiliary-gauge", choices=("raw", "positive-h"), default="raw")
    parser.add_argument("--dtn-phase-gauge", choices=("global_z", "boundary_plane"), default="global_z")
    parser.add_argument("--dense-authority", type=Path)
    parser.add_argument("--dense-authority-report-sha256")
    parser.add_argument("--expected-head")
    parser.add_argument("--run-directory", type=Path)
    parser.add_argument("--bridge-report", type=Path)
    parser.add_argument("--bridge-report-sha256")
    args = parser.parse_args()
    if not args.run:
        print(json.dumps({"status": "NOT_RUN_STAGED_PLAN_ONLY", "degree": args.degree,
                          "auxiliary_gauge": args.auxiliary_gauge,
                          "scope": "same 80-cell full3D exact condensation, all q and physical aliases",
                          "tree_cap_bytes": TREE_CAP_BYTES, "wall_seconds": WALL_SECONDS,
                          "required": ["parent staged-source review", "clean own-branch integration commit",
                                       "qualified tests and complex ABI", "p2 bridge then independent checker before p4"]}, indent=2))
        return 0
    if not args.expected_head or not args.run_directory:
        parser.error("run requires the exact clean integrated commit and a new ignored artifact directory")
    if args.dtn_phase_gauge == "boundary_plane" and (args.degree != 2 or args.auxiliary_gauge != "positive-h"
            or not args.dense_authority or not args.dense_authority_report_sha256):
        parser.error("centered extension requires p2 positive-H and a fresh passed dense authority; p4 remains held")
    if args.dtn_phase_gauge == "global_z" and (args.dense_authority or args.dense_authority_report_sha256):
        parser.error("centered authority cannot authorize a legacy global-z run")
    args.run_directory = args.run_directory.resolve()
    if not args.run_directory.is_relative_to(ARTIFACT_ROOT.resolve()):
        parser.error("artifacts must remain in the own ignored subtree")
    source = source_facts(args.expected_head)
    environment = environment_facts()
    if file_sha256(INPUT) != INPUT_SHA:
        raise RuntimeError("inherited input hash mismatch")
    if args.degree == 4:
        if args.auxiliary_gauge == "positive-h":
            parser.error("same-discrete positive-H diagnostic is p2-only; p4 is held for boundary-gauge review")
        if not args.bridge_report or not args.bridge_report_sha256:
            parser.error("p4 requires a same-source passed sparse-p2 bridge and independent checker")
        args.bridge_report = args.bridge_report.resolve()
        _validate_bridge(args.bridge_report, args.bridge_report_sha256, args.expected_head, source)
    elif args.dtn_phase_gauge == "boundary_plane":
        SavedCenteredDenseP2Authority(args.dense_authority,args.dense_authority_report_sha256,source,environment)
    else:
        SavedDenseP2Authority(environment)
    if args.worker:
        return _worker(args)
    if shutil.disk_usage(ROOT).free < 2 * 1024**3:
        raise RuntimeError("bounded evidence run requires at least 2GiB free disk")
    from benchmarks.subreaper_watchdog import supervise
    command = [sys.executable, "-m", "benchmarks.run_y_orbit_sparse_probe", "--run", "--worker",
               "--degree", str(args.degree), "--expected-head", args.expected_head,
               "--run-directory", str(args.run_directory), "--auxiliary-gauge", args.auxiliary_gauge,
               "--dtn-phase-gauge", args.dtn_phase_gauge]
    if args.dtn_phase_gauge == "boundary_plane":
        command += ["--dense-authority",str(args.dense_authority),
                    "--dense-authority-report-sha256",args.dense_authority_report_sha256]
    if args.degree == 4:
        command += ["--bridge-report", str(args.bridge_report),
                    "--bridge-report-sha256", args.bridge_report_sha256]
    summary = supervise(command, args.run_directory, wall_seconds=WALL_SECONDS, interval=.25,
                        grace_seconds=2, source_state=source, phase_path=args.run_directory / "phase.json",
                        tree_cap_bytes=TREE_CAP_BYTES, hard_stop_immediate=True, timebase_guard=True,
                        stop_on_global_swap=True, pss_sampling_policy="disabled_by_profile")
    print(json.dumps(summary, allow_nan=False, indent=2), flush=True)
    report = args.run_directory / "probe_report.json"
    return 0 if (summary["classification"] == "COMPLETED" and report.is_file()
                 and json.loads(report.read_text())["status"] == "SPARSE_CONDENSED_FULL3D_PROBE_PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
