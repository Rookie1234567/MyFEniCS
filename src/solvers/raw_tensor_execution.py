"""Explicit single-MPI-rank, many-exec-worker exact tensor execution policy."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from .parallel_tensor_cache import digest, key_for, load_shard, run_batch


def evaluate_raw_classes(policy_forms, coordinates, ordered_keys, config):
    """Precompute classes independently; return in the existing canonical order.

    Only coefficient-free cell integrals are supported. The existing parent
    remains responsible for orientations, local solves, MPC and PETSc assembly.
    """
    required = {"root", "cpus", "operator_identity"}
    if required - config.keys():
        raise ValueError(
            "raw tensor execution requires root, cpus and operator identity"
        )
    cpus = list(map(int, config["cpus"]))
    if len(cpus) not in (1, 2, 4, 8, 16, 32) or len(set(cpus)) != len(cpus):
        raise ValueError("raw tensor execution supports 1/2/4/8/16/32 distinct CPUs")
    root = Path(config["root"]).resolve()
    jobs = []
    modules = {}
    for key in ordered_keys:
        compiled, kernels, dimension = policy_forms[str(key[0])]
        module = compiled.module
        module_path = str(Path(module.__file__).resolve())
        if module_path not in modules:
            signature = module.ffi.string(compiled.ufcx_form.signature)
            symbols = [
                name
                for name in dir(module.lib)
                if name.startswith("form_")
                and module.ffi.string(getattr(module.lib, name).signature) == signature
            ]
            if len(symbols) != 1:
                raise ValueError("compiled form has no unique exact symbol")
            modules[module_path] = (digest(module_path), symbols[0])
        module_sha, symbol = modules[module_path]
        if compiled.ufcx_form.num_coefficients or compiled.ufcx_form.num_constants:
            raise ValueError(
                "parallel raw tensors require embedded constant coefficients"
            )
        jobs.append(
            {
                "coordinates": np.asarray(coordinates[key], dtype=np.float64)
                .reshape(8, 3)
                .tolist(),
                "dimension": int(dimension),
                "tag": int(key[1]),
                "module_name": module.__name__,
                "module_path": module_path,
                "module_sha256": module_sha,
                "form_symbol": symbol,
                "operator_identity": {
                    **config["operator_identity"],
                    "form_signature": module.ffi.string(
                        compiled.ufcx_form.signature
                    ).decode(),
                    "element_hash": int(
                        compiled.function_spaces[0].element.basix_element.hash()
                    ),
                    "kernel_ids": sorted(map(int, kernels)),
                    "scalar": "complex128",
                },
            }
        )
    started = time.perf_counter()
    result = run_batch(
        jobs,
        root,
        cpus,
        timeout=config.get("job_timeout_seconds"),
        progress=config.get("progress"),
        available_floor=int(config.get("minimum_available_bytes", 68719476736)),
        disk_reserve=int(config.get("disk_reserve_bytes", 10737418240)),
    )
    arrays = {}
    for key, job in zip(ordered_keys, jobs, strict=True):
        shard = load_shard(root, job)
        arrays[key] = np.load(shard["path"], mmap_mode="r", allow_pickle=False)
    audit = {
        "backend": "exact_exec_tensor_cache_v1",
        "requested_workers": len(cpus),
        "effective_max_workers": min(len(cpus), len(result)),
        "cpus": cpus,
        "unique_classes": len(result),
        "cache_hits": sum(bool(item["cache_hit"]) for item in result.values()),
        "computed_classes": sum(not item["cache_hit"] for item in result.values()),
        "wall_seconds": time.perf_counter() - started,
        "kernel_cpu_seconds_sum": sum(
            item.get("kernel_cpu_seconds", 0) for item in result.values()
        ),
        "root": str(root),
        "payload_keys": [key_for(job) for job in jobs],
        "global_insertion_order": "unchanged_canonical_order",
    }
    return arrays, audit
