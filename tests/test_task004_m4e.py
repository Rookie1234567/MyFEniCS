"""Small pure-Python contracts for the Task004 M4E implementation."""

import json
from pathlib import Path

import numpy as np

from src.surrogate.angle.m4e import _aggregate, _latent, candidate_specs, _load_windows


ROOT = Path(__file__).resolve().parents[1]
TRAIN = ROOT / "benchmarks/artifacts/cases/125_task004_angle_training_qualification/train96"
WINDOWS = ROOT / "surrogate_tasks/task004_nominal_geometry_angle_surrogate/outcomes/SUPPORTED_INTERPOLATION_WINDOWS_V2.json"


def test_m4e_composition_latent_round_trip():
    aggregate = np.asarray([[0.2, 0.3, 0.5], [0.01, 0.49, 0.5]], dtype=np.float64)
    latent = _latent(aggregate)
    restored = _aggregate(latent)
    assert np.allclose(restored, aggregate, atol=1.0e-7)
    assert np.allclose(np.sum(restored, axis=1), 1.0, atol=1.0e-12)


def test_m4e_candidate_set_is_finite_and_review_bounded():
    specs = candidate_specs()
    assert len(specs) == 8
    assert {spec["family"] for spec in specs} == {
        "local_rbf", "local_matern", "topology_expert", "trend_local_residual",
    }
    assert {spec["neighbors"] for spec in specs if spec["family"] in {
        "local_rbf", "local_matern",
    }} == {24, 32, 48}


def test_m4e_supported_windows_have_disjoint_support():
    angles = np.load(TRAIN / "angles.npy", allow_pickle=False)
    manifest = json.loads((TRAIN / "dataset_manifest.json").read_text())
    windows = _load_windows(WINDOWS, angles, manifest["training_tuple_sha256"])
    assert set(windows) == {"low_grazing", "high_azimuth", "cutoff_near", "ordinary_interior"}
