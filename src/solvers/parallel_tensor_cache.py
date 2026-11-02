"""Exact raw-cell tensors via opt-in fresh executables and disk shards.

No MPI, DOLFINx mesh, PETSc matrix, or global assembly is imported here.
Full-case qualification is separate from bounded component validation.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import fcntl
import hashlib
import importlib.util
import json
import os
import queue
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

SCHEMA = "exact-raw-cell-tensor.v1"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def identity(job):
    coordinates = np.asarray(job["coordinates"], dtype="<f8")
    if coordinates.shape != (8, 3) or not np.isfinite(coordinates).all():
        raise ValueError("expected finite exact 8x3 Q1 coordinates")
    dimension = int(job["dimension"])
    if dimension < 1 or dimension > 4096:
        raise ValueError("invalid bounded tensor dimension")
    if not job["operator_identity"]:
        raise ValueError("explicit operator/ABI identity required")
    result = {
        "schema": SCHEMA,
        "module_sha256": job["module_sha256"],
        "form_symbol": job["form_symbol"],
        "tag": int(job["tag"]),
        "dimension": dimension,
        "dtype": "<c16",
        "coordinates_le_f64": coordinates.tobytes().hex(),
        "operator_identity": job["operator_identity"],
    }
    # Reject NaN in metadata as well. No coordinate rounding or material merging.
    json.dumps(result, sort_keys=True, allow_nan=False)
    return result


def key_for(job):
    return hashlib.sha256(
        json.dumps(
            identity(job), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_shard(root, job):
    folder = Path(root) / key_for(job)
    marker = folder / "complete.json"
    if not marker.exists():
        return None  # An interrupted write without a commit marker is not a hit.
    metadata = json.loads(marker.read_text())
    if metadata["identity"] != identity(job):
        raise ValueError("cache identity mismatch")
    payload = folder / "tensor.npy"
    if digest(payload) != metadata["payload_sha256"]:
        raise ValueError("cache payload hash mismatch")
    array = np.load(payload, allow_pickle=False, mmap_mode="r")
    n = int(job["dimension"])
    if array.shape != (n, n) or array.dtype != np.dtype("<c16"):
        raise ValueError("cache tensor shape/dtype mismatch")
    if not np.isfinite(array).all():
        raise ValueError("cache tensor contains nonfinite values")
    return {"key": key_for(job), "path": str(payload), "metadata": metadata}


def commit_shard(root, job, tensor, facts):
    folder = Path(root) / key_for(job)
    folder.mkdir(parents=True, exist_ok=True)
    n = int(job["dimension"])
    tensor = np.asarray(tensor)
    if (
        tensor.shape != (n, n)
        or tensor.dtype != np.dtype("<c16")
        or not np.isfinite(tensor).all()
    ):
        raise ValueError("refusing invalid tensor commit")
    fd, temporary = tempfile.mkstemp(prefix=".tensor-", dir=folder)
    try:
        with os.fdopen(fd, "wb") as stream:
            np.save(stream, tensor, allow_pickle=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, folder / "tensor.npy")
        metadata = {
            "identity": identity(job),
            "payload_sha256": digest(folder / "tensor.npy"),
            "facts": facts,
        }
        atomic_json(folder / "complete.json", metadata)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def compute_one(job, root, cpu, available_floor, disk_reserve):
    """Fresh process entry. Per-key lock prevents concurrent duplicate writers."""
    os.sched_setaffinity(0, {int(cpu)})
    os.nice(19)
    folder = Path(root) / key_for(job)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "writer.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        cached = load_shard(root, job)
        if cached is not None:
            return {"key": key_for(job), "cache_hit": True}
        available = (
            int(
                next(
                    line.split()[1]
                    for line in Path("/proc/meminfo").read_text().splitlines()
                    if line.startswith("MemAvailable:")
                )
            )
            * 1024
        )
        if available < available_floor:
            raise RuntimeError("host available floor not satisfied")
        if (
            shutil.disk_usage(root).free
            < disk_reserve + int(job["dimension"]) ** 2 * 16
        ):
            raise RuntimeError("disk reserve not satisfied")
        if digest(job["module_path"]) != job["module_sha256"]:
            raise ValueError("compiled module changed")
        spec = importlib.util.spec_from_file_location(
            job["module_name"], job["module_path"]
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        form = getattr(module.lib, job["form_symbol"])
        if form.num_coefficients or form.num_constants:
            raise ValueError("runtime coefficient/constant forms are unsupported")
        # Same default-then-material order as _tabulate_raw_tensor_class.
        kernels = []
        for tag in (-1, int(job["tag"])):
            kernels.extend(
                form.form_integrals[i].tabulate_tensor_complex128
                for i in range(
                    form.form_integral_offsets[0], form.form_integral_offsets[1]
                )
                if form.form_integral_ids[i] == tag
            )
        if not kernels or any(kernel == module.ffi.NULL for kernel in kernels):
            raise ValueError("no valid complex128 kernel for material")
        coordinates = np.ascontiguousarray(job["coordinates"], dtype=np.float64)
        n = int(job["dimension"])
        result = np.zeros((n, n), dtype=np.complex128)
        started = time.perf_counter()
        cpu_started = time.process_time()
        ffi = module.ffi
        for kernel in kernels:
            contribution = np.zeros_like(result)
            kernel(
                ffi.cast("double _Complex *", ffi.from_buffer(contribution)),
                ffi.NULL,
                ffi.NULL,
                ffi.cast("double *", ffi.from_buffer(coordinates)),
                ffi.NULL,
                ffi.NULL,
                ffi.NULL,
            )
            result += contribution
        facts = {
            "kernel_wall_seconds": time.perf_counter() - started,
            "kernel_cpu_seconds": time.process_time() - cpu_started,
            "pid": os.getpid(),
            "affinity": sorted(os.sched_getaffinity(0)),
            "worker_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            * 1024,
            "kernel_count": len(kernels),
        }
        commit_shard(root, job, result, facts)
        return {"key": key_for(job), "cache_hit": False, **facts}


def run_batch(
    jobs,
    root,
    cpus,
    *,
    timeout=None,
    progress=None,
    available_floor=68_719_476_736,
    disk_reserve=10_737_418_240,
):
    """Return key-sorted results; worker completion order never defines assembly order."""
    cpus = tuple(map(int, cpus))
    if not cpus or len(set(cpus)) != len(cpus):
        raise ValueError("nonempty distinct admitted CPUs required")
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    unique = {key_for(job): job for job in jobs}
    module_hashes = {}
    for job in unique.values():
        path = str(Path(job["module_path"]).resolve())
        if path not in module_hashes:
            module_hashes[path] = digest(path)
        if module_hashes[path] != job["module_sha256"]:
            raise ValueError("compiled module changed, including for cache hits")
    free_cpus = queue.Queue()
    for cpu in cpus:
        free_cpus.put(cpu)
    results = {}

    def execute(job):
        cached = load_shard(root, job)
        if cached is not None:
            return {"key": key_for(job), "cache_hit": True}
        cpu = free_cpus.get()
        try:
            request = root / (key_for(job) + ".request.json")
            atomic_json(request, job)
            env = {
                **os.environ,
                **{
                    name: "1"
                    for name in (
                        "OMP_NUM_THREADS",
                        "OPENBLAS_NUM_THREADS",
                        "MKL_NUM_THREADS",
                        "BLIS_NUM_THREADS",
                        "NUMEXPR_NUM_THREADS",
                        "VECLIB_MAXIMUM_THREADS",
                    )
                },
            }
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--job",
                str(request),
                "--root",
                str(root),
                "--cpu",
                str(cpu),
                "--floor",
                str(available_floor),
                "--disk-reserve",
                str(disk_reserve),
            ]
            completed = subprocess.run(
                command,
                env=env,
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout,
            )
            answer = json.loads(completed.stdout)
            if load_shard(root, job) is None:
                raise RuntimeError("worker returned without a committed tensor")
            return answer
        finally:
            free_cpus.put(cpu)

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(cpus)) as pool:
        futures = {pool.submit(execute, job): key for key, job in unique.items()}
        for future in concurrent.futures.as_completed(futures):
            answer = future.result()
            results[answer["key"]] = answer
            if progress is not None:
                progress(len(results), len(unique), answer)
    return {key: results[key] for key in sorted(results)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--cpu", type=int, required=True)
    parser.add_argument("--floor", type=int, required=True)
    parser.add_argument("--disk-reserve", type=int, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            compute_one(
                json.loads(Path(args.job).read_text()),
                args.root,
                args.cpu,
                args.floor,
                args.disk_reserve,
            )
        )
    )
