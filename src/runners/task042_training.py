"""Isolated Task042 CPU training entry; no FE/native imports."""

import hashlib
import os
from pathlib import Path

import numpy as np

from src.solvers.learned_training import train


def main():
    import json
    import sys

    from src.io import load_and_resolve
    from src.runners.task042_shared import ARTIFACTS, ROOT, write_json

    specification = load_and_resolve(sys.argv[1])
    directory = Path(sys.argv[2])
    run = json.loads((directory / "run_manifest.json").read_text())
    profile = json.loads(
        (
            ROOT / "input/task042_neural_coarse_inverse/shared_profile_v1.json"
        ).read_text()
    )
    proof = profile["oracle_qualification"]
    previous = ROOT / proof["directory"]
    resources = json.loads((previous / "run_summary.json").read_text())
    numerical = json.loads((previous / "numerical_summary.json").read_text())
    if (
        not resources["descendants_cleared"]
        or resources["leader_exit_code"] != 0
        or numerical["status"] != "REPRESENTATION_POSITIVE"
    ):
        raise ValueError("Oracle prerequisite not qualified or released")
    path = Path(numerical["oracle_manifest"])
    if hashlib.sha256(path.read_bytes()).hexdigest() != proof["manifest_sha256"]:
        raise ValueError("Frozen oracle manifest changed")
    oracle = json.loads(path.read_text())
    if (
        oracle["heldout_used_for_selection"]
        or oracle["registered_deployment_rank"] != 128
    ):
        raise ValueError("Oracle representation/split differs")
    features_path = Path(oracle["features_path"])
    if (
        hashlib.sha256(features_path.read_bytes()).hexdigest()
        != oracle["features_sha256"]
    ):
        raise ValueError("Training features changed")
    with np.load(features_path, allow_pickle=False) as packet:
        if any("heldout" in key for key in packet.files):
            raise ValueError("Heldout data leaked to training")
        features = {key: packet[key] for key in packet.files}
    if (
        os.environ.get("TASK042_ENV_MODE") != "ml"
        or str(ROOT / ".venv-ml") not in sys.executable
    ):
        raise ValueError("Independent Task042 CPU ML environment required")
    libraries = [
        line.split()[-1]
        for line in Path("/proc/self/maps").read_text().splitlines()
        if "/" in line
    ]
    if any(
        any(name in lib for name in ("libpetsc", "libdolfin", "libmpi.so"))
        for lib in libraries
    ):
        raise ValueError("FE libraries contaminated ML worker")
    artifact = ARTIFACTS / directory.name
    artifact.mkdir()
    result = {
        "status": "STARTED",
        "stage": "F3-train",
        "source_sha": run["source_sha"],
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "oracle_manifest_sha256": proof["manifest_sha256"],
        "oracle_source_sha": oracle["source_sha"],
        "dataset_manifest_sha256": oracle["dataset_manifest_sha256"],
        "features_sha256": oracle["features_sha256"],
        "basis_sha256": oracle["basis_sha256"],
        "official_result": None,
        "shared_workstation": True,
    }
    try:
        summary = train(features, artifact, run["source_sha"], write_json)
        result.update(
            summary,
            model_path=str(artifact / "frozen_model.npz"),
            model_manifest=str(artifact / "training_summary.json"),
        )
    except BaseException as exc:
        result.update(status="FAILED", error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        write_json(directory / "numerical_summary.json", result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
