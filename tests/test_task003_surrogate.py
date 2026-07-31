from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from surrogate.dataset import CASE119_ROOT, load_training_dataset, verify_case119_dataset
from surrogate.features import transform_feature_candidate, transform_features
from surrogate.folds import FOLD_SEED, fold_identity, folds
from surrogate.models import ExactARDGP, PolynomialPCE, deterministic_optimization_initials
from surrogate.physics import analytic_power_mask, reconstruct_aggregates
from surrogate.targets import aggregate_composition, aggregate_log_ratios, freeze_power_floor


def test_case119_hash_and_array_identity():
    result = verify_case119_dataset(CASE119_ROOT)
    assert result.dataset_id == "task002_m4e_p5_ny4_112_v3"
    assert result.sample_count == 112
    assert result.training_count == 96
    assert result.frozen_validation_count == 16
    assert result.validation_target_accessed is False
    assert result.arrays["order_powers.npy"] == {"shape": [112, 22, 2], "dtype": "float64"}


def test_default_loader_does_not_open_frozen_index(monkeypatch):
    original = np.load
    opened: list[str] = []

    def guarded_load(path, *args, **kwargs):
        opened.append(str(path))
        assert "frozen_validation" not in str(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(np, "load", guarded_load)
    dataset = load_training_dataset(CASE119_ROOT)
    assert dataset.n_samples == 96
    assert all("frozen_validation" not in path for path in opened)


def test_analytic_mask_matches_training_rows():
    dataset = load_training_dataset(CASE119_ROOT)
    assert np.array_equal(analytic_power_mask(dataset.inputs), dataset.power_carrying_mask)


def test_domain_and_zero_grazing_fail_closed():
    with pytest.raises(ValueError):
        transform_features(np.array([[120.0, 17.0, 0.0, 45.0]]))
    with pytest.raises(ValueError):
        transform_features(np.array([[120.0, 17.0, 11.0, 45.0]]))


def test_folds_are_deterministic_and_cover_training_only():
    dataset = load_training_dataset(CASE119_ROOT)
    x = transform_features(dataset.inputs)
    first = folds(x, seed=FOLD_SEED)
    second = folds(x, seed=FOLD_SEED)
    assert fold_identity(x, first) == fold_identity(x, second)
    assert sorted(np.concatenate([test for _, test in first]).tolist()) == list(range(96))


def test_cpu_models_repeat_exactly():
    dataset = load_training_dataset(CASE119_ROOT)
    x = transform_features(dataset.inputs)
    y = dataset.aggregates[:, 0]
    a = ExactARDGP(optimizer_restarts=8, random_state=0).fit(x, y).predict(x)
    b = ExactARDGP(optimizer_restarts=8, random_state=0).fit(x, y).predict(x)
    assert np.array_equal(a, b)
    pce = PolynomialPCE(2).fit(x, y)
    assert np.all(np.isfinite(pce.predict(x)))
    assert pce.metadata()["basis"] == "legendre"


def test_m3r_feature_candidates_and_log_ratio_contract():
    dataset = load_training_dataset(CASE119_ROOT)
    assert transform_feature_candidate(dataset.inputs, "A").shape == (96, 4)
    assert transform_feature_candidate(dataset.inputs, "B").shape == (96, 4)
    assert transform_feature_candidate(dataset.inputs, "C").shape == (96, 5)
    latent = aggregate_log_ratios(dataset.aggregates)
    reconstructed = aggregate_composition(latent)
    assert np.allclose(reconstructed[:, :3].sum(axis=1), 1.0, atol=1e-12)
    assert np.max(np.abs(reconstructed[:, :3] - dataset.aggregates[:, :3])) < 1.0e-6


def test_gp_has_auditable_multistart_metadata_and_floor():
    dataset = load_training_dataset(CASE119_ROOT)
    x = transform_features(dataset.inputs)
    model = ExactARDGP(optimizer_restarts=8, random_state=0).fit(x, dataset.aggregates[:, 0])
    metadata = model.metadata()
    assert len(metadata["optimization_runs"]) == 8
    assert all("fitted_kernel" in run and "log_marginal_likelihood" in run
               and "boundary_collisions" in run and "optimizer_status" in run
               for run in metadata["optimization_runs"])
    assert freeze_power_floor(dataset.order_powers[:, 7, 0],
                              dataset.power_carrying_mask[:, 7, 0]) >= 1.0e-12
    assert len(deterministic_optimization_initials(5, 8, 0)) == 8


def test_composition_reconstruction_conserves_power():
    raw = np.array([[0.2, 0.3, 0.4], [2.0, 1.0, 0.5]])
    result = reconstruct_aggregates(raw)
    assert np.all(result >= 0.0)
    assert np.allclose(result[:, :3].sum(axis=1), 1.0, atol=1e-12)
    assert np.array_equal(result[:, 2], result[:, 3])
