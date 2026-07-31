"""Task003 M0-L local CPU verification and exact-GP smoke command."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import time
import io
import contextlib
from pathlib import Path
from typing import Any

import numpy as np
import psutil
import scipy
import sklearn

from .dataset import CASE119_ROOT, load_training_dataset, verify_case119_dataset
from .features import transform_features
from .models import ExactARDGP


TASK003_ROOT = Path("surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training")
OUTCOMES_ROOT = TASK003_ROOT / "outcomes"


def _json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def _swap() -> dict[str, int]:
    value = psutil.swap_memory()
    return {"total_bytes": int(value.total), "used_bytes": int(value.used),
            "free_bytes": int(value.free)}


def _max_rss_bytes() -> int:
    # Linux ru_maxrss is KiB; this remains valid in WSL2.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _venv_fingerprint(path: Path) -> dict[str, Any]:
    stat = path.stat()
    cfg = path / "pyvenv.cfg"
    return {"path": str(path), "exists": path.exists(), "mtime_ns": stat.st_mtime_ns,
            "inode": stat.st_ino,
            "pyvenv_cfg_sha256": hashlib.sha256(cfg.read_bytes()).hexdigest()
            if cfg.exists() else None}


def environment_manifest() -> dict[str, Any]:
    thread_names = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS")
    versions = {"python": platform.python_version(), "numpy": np.__version__,
                "scipy": scipy.__version__, "scikit_learn": sklearn.__version__,
                "psutil": psutil.__version__}
    blas_stream = io.StringIO()
    with contextlib.redirect_stdout(blas_stream):
        np.__config__.show()
    return {
        "backend": "local_wsl2_cpu",
        "cuda_used": False,
        "python_executable": str(Path(sys.executable).resolve()),
        "versions": versions,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "thread_environment": {name: os.environ.get(name) for name in thread_names},
        "max_parallel_model_fits": 1,
        "blas_configuration": blas_stream.getvalue().strip(),
        "fem_venv_fingerprint": _venv_fingerprint(Path(".venv")),
        "cpu_venv_fingerprint": _venv_fingerprint(Path(".venv-surrogate-cpu")),
        "source_sha": _git_head(),
    }


def run_smoke(*, repeats: int = 2) -> dict[str, Any]:
    dataset = load_training_dataset(CASE119_ROOT)
    x = transform_features(dataset.inputs)
    y = dataset.aggregates[:, 0]  # one aggregate quantity, R_total
    runs: list[dict[str, Any]] = []
    prediction_hashes: list[str] = []
    for repeat in range(repeats):
        before_swap = _swap()
        before_rss = _max_rss_bytes()
        start = time.perf_counter()
        model = ExactARDGP(jitter=1.0e-10, optimizer_restarts=0,
                           random_state=0).fit(x, y)
        prediction, std = model.predict(x, return_std=True)
        elapsed = time.perf_counter() - start
        after_swap = _swap()
        prediction_hash = hashlib.sha256(
            np.ascontiguousarray(prediction).tobytes() +
            np.ascontiguousarray(std).tobytes()
        ).hexdigest()
        prediction_hashes.append(prediction_hash)
        runs.append({
            "repeat": repeat + 1,
            "fit_predict_wall_seconds": elapsed,
            "rss_before_bytes": before_rss,
            "peak_rss_bytes": _max_rss_bytes(),
            "swap_before": before_swap,
            "swap_after": after_swap,
            "swap_delta_bytes": after_swap["used_bytes"] - before_swap["used_bytes"],
            "prediction_sha256": prediction_hash,
            "fitted_kernel": model.kernel_,
            "n_samples": dataset.n_samples,
            "target": "aggregates.R_total",
        })
    return {
        "status": "pass" if len(set(prediction_hashes)) == 1 else "fail",
        "model": ExactARDGP(jitter=1.0e-10).metadata(),
        "repeats": runs,
        "reproducible": len(set(prediction_hashes)) == 1,
        "swap_clean": all(row["swap_delta_bytes"] == 0 for row in runs),
        "validation_target_accessed": False,
    }


def run_m0() -> dict[str, Any]:
    verification = verify_case119_dataset(CASE119_ROOT)
    environment = environment_manifest()
    smoke = run_smoke()
    result = {
        "status": "pass" if smoke["status"] == "pass" else "fail",
        "source_sha": _git_head(),
        "dataset_verification": verification.as_dict(),
        "environment": environment,
        "smoke": smoke,
        "frozen_validation_access": {"status": "sealed", "target_rows_loaded": False,
                                      "unlock_flag": "--unlock-frozen-validation",
                                      "model_selection_lock_required": True},
    }
    _json_dump(OUTCOMES_ROOT / "LOCAL_DATASET_VERIFICATION.json",
               verification.as_dict())
    _json_dump(OUTCOMES_ROOT / "LOCAL_CPU_ENVIRONMENT.json", environment)
    _json_dump(OUTCOMES_ROOT / "M0L_CPU_SMOKE.json", smoke)
    _json_dump(OUTCOMES_ROOT / "M0L_report.json", result)
    return result


if __name__ == "__main__":
    print(json.dumps(run_m0(), indent=2, ensure_ascii=False))
