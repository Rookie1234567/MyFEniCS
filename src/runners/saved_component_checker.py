"""Recheck frozen W0 raw with the unchanged mathematical checker.

Only the local saved-array I/O path and this process's soft FD admission differ.
No mesh, form, FE worker, global Maxwell factor or new reference is constructed.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import sys


def descriptor_budget(member_count, *, reserve=128):
    """Bound own descriptors below the existing hard limit; never change hard."""
    if type(member_count) is not int or member_count <= 0:
        raise ValueError("positive actual saved member count required")
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    required = 2 * member_count + reserve
    target = 1 << (required - 1).bit_length()
    if hard != resource.RLIM_INFINITY and required > hard:
        raise RuntimeError("FD_CAPACITY_UNAVAILABLE_WITHIN_EXISTING_HARD_LIMIT")
    target = max(soft, min(target, hard)) if hard != resource.RLIM_INFINITY else max(soft, target)
    resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    return {"soft_before": soft, "soft_after": target, "hard_unchanged": hard,
            "member_count": member_count, "reserved_descriptors": reserve,
            "conservative_descriptors_per_member": 2,
            "scope": "this checker process and its children only"}


def canonical_saved_path(producer, reference):
    name, location = reference.get("name"), reference.get("callback_reference")
    if not isinstance(name, str) or not isinstance(location, str):
        raise ValueError("saved raw reference lacks its frozen name/path")
    expected = Path(producer).resolve() / "raw" / (hashlib.sha256(name.encode()).hexdigest() + ".npy")
    if Path(location) != expected or expected.is_symlink() or not expected.is_file():
        raise ValueError("saved raw path is outside the frozen producer")
    return expected


class SavedArrayLoader:
    """Map each frozen canonical member once; aliases reuse readonly storage."""
    def __init__(self, producer):
        self.producer, self.cache, self.requests = Path(producer), {}, 0

    def __call__(self, reference):
        import numpy as np

        path = canonical_saved_path(self.producer, reference)
        self.requests += 1
        value = self.cache.get(reference["name"])
        if value is None:
            value = np.load(path, mmap_mode="r", allow_pickle=False)
            self.cache[reference["name"]] = value
        if (list(value.shape) != reference.get("shape") or str(value.dtype) != reference.get("dtype")
                or value.flags.writeable):
            raise ValueError("saved array shape/dtype/readonly binding changed")
        return value

    def close(self):
        for value in self.cache.values():
            value._mmap.close()
        self.cache.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("frozen-source", "producer", "output-dir", "abi-receipt", "worker-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    source, producer, output = map(Path, (args.frozen_source, args.producer, args.output_dir))
    encoded = (producer / "worker_report.json").read_bytes()
    if hashlib.sha256(encoded).hexdigest() != args.worker_sha256:
        raise ValueError("frozen completed worker hash changed")
    report = json.loads(encoded)
    # Numerical imports happen only after the qualified native activation.
    sys.path.insert(0, str(source.resolve()))
    from benchmarks.run_fresh_c1_p6_component import (
        _atomic_json, _disk_facts, _native_callbacks, _qualified_runtime,
    )
    _mpi, _petsc, identity = _qualified_runtime(Path(args.abi_receipt))
    fd = descriptor_budget(len(report["snapshot"]["members"]))
    _atomic_json(output / "descriptor_admission.json", fd)
    disk = _disk_facts(producer)
    if disk["stop"]:
        raise RuntimeError("frozen producer raw/disk budget is not admissible")
    allocation_gate, _unused, checkpoint, _guard = _native_callbacks(output, checker=True)
    from benchmarks.check_fresh_c1_p6_component import check_component
    loader = SavedArrayLoader(producer)
    try:
        result = check_component(report, loader, allocation_gate=allocation_gate,
                                 checkpoint=checkpoint, runtime_profile=identity["runtime_profile"])
        io_cost = {"load_requests": loader.requests, "unique_mappings": len(loader.cache),
                   "open_descriptors_before_release": len(list(Path("/proc/self/fd").iterdir()))}
    finally:
        loader.close()
    _atomic_json(output / "checker_report.json", result)
    _atomic_json(output / "run_summary.json", {
        "status": "PASS_SAVED_COMPONENT_CHECK" if result["independent_component_pass"] else "CHECKER_FAILED",
        "producer": str(producer.resolve()), "worker_report_sha256": args.worker_sha256,
        "math_checker_file_sha256": hashlib.sha256((source / "benchmarks/check_fresh_c1_p6_component.py").read_bytes()).hexdigest(),
        "descriptor_budget": fd, "FE_worker_replayed": False,
        "saved_array_IO": io_cost,
        "PDE_solved": False, "official_results": False,
        "parent_pid": os.getppid(), "checker_pid": os.getpid(),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
