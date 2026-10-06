"""Independent frozen evaluation: exact zeros, complete maps and damaged state."""

import json

import numpy as np
import pytest

from src.postprocessing.neural_wave_frozen_field import (
    frozen_point_values,
    rebuild_frozen_field,
)
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz, sha
from src.solvers.neural_wave_moments import Patch
from src.solvers.neural_wave_reconstruction import pointwise_moments, rebuild
from src.test.test_neural_wave import tensor_fixture


@pytest.mark.parametrize("width", [1, 2, 4, 8])
def test_independent_all_families_orientation_and_owner_pair(width):
    rng, packet = tensor_fixture()
    packet["owner_rows"][1, ::11] = -1
    models = []
    for center, radius in [
        ((0.5, 0.5, 0.0), (0.5, 0.5, 0.7)),
        ((1.0, 0.0, 0.0), (1.0, 1.3, 0.7)),
        ((9.0, 9.0, 9.0), (0.25, 0.25, 0.25)),
    ]:
        models.append(
            (
                Patch(center, radius),
                rng.normal(size=(width, 3)),
                rng.normal(size=(width, 3)) + 1j * rng.normal(size=(width, 3)),
            )
        )

    def independent_unmasked(points):
        values = np.zeros(points.shape, dtype=np.complex128)
        for patch, q, amplitude in models:
            values += patch.window(points)[:, None] * (
                np.exp(1j * (points - patch.center) @ q.T) @ amplitude
            )
        return values

    expected = pointwise_moments(packet, independent_unmasked)
    actual = pointwise_moments(packet, lambda x: frozen_point_values(models, x))
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
    for family in (slice(0, 36), slice(36, 108), slice(108, 144)):
        assert np.linalg.norm(actual[family]) > 0


def test_arbitrarily_small_nonzero_window_is_retained():
    points = np.array(
        [[np.nextafter(1.0, 0.0), 0.0, 0.0], [1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]]
    )
    patch = Patch((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    amplitude = np.array([[1.0 + 2j, -3j, 2.0]])
    counts = dict(
        bbox_skipped_models=0,
        exact_zero_point_neurons_omitted=0,
        nonzero_point_neurons_evaluated=0,
    )
    actual = frozen_point_values([(patch, np.zeros((1, 3)), amplitude)], points, counts)
    expected = patch.window(points)[:, None] * amplitude
    np.testing.assert_array_equal(actual, expected)
    assert 0 < np.linalg.norm(actual[0]) < 1e-20
    assert np.count_nonzero(actual[1:]) == 0
    assert counts["exact_zero_point_neurons_omitted"] == 2
    assert counts["nonzero_point_neurons_evaluated"] == 1


def saved_fixture(tmp_path):
    rng, packet = tensor_fixture()
    a = np.array([0.6 + 0.3j, -0.2 + 0.1j])
    chunks = []
    for i, width in enumerate((2, 8)):
        file = tmp_path / f"module{i}.npz"
        amplitude = rng.normal(size=(width, 3)) + 1j * rng.normal(size=(width, 3))
        atomic_npz(
            file,
            center=np.array([0.5, 0.5, 0.0]),
            radius=np.array([1.0, 1.3, 0.7]),
            wave_q=rng.normal(size=(width, 3)),
            amplitude_real=amplitude.real,
            amplitude_imag=amplitude.imag,
            scale=np.array(0.37 + i),
        )
        chunks.append(dict(path=file.name, sha256=sha(file)))
    state = tmp_path / "state.npz"
    # Deliberately wrong saved c: both rebuilds must compute from the model.
    atomic_npz(state, a=a, c=np.ones(packet["active_rows"], dtype=np.complex128))
    boundary = dict(
        columns=2,
        chunks=chunks,
        state=dict(path=state.name, sha256=sha(state)),
        binding=dict(source_sha="f" * 40, reference_used_for_training=False),
    )
    atomic_json(tmp_path / "committed.json", boundary)
    return packet, boundary


def test_saved_network_coefficients_are_actually_rebuilt(tmp_path):
    packet, _ = saved_fixture(tmp_path)
    expected, saved, old = rebuild(tmp_path, packet)
    actual, reread, new = rebuild_frozen_field(tmp_path, packet)
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(saved, reread)
    assert new == old
    assert np.linalg.norm(actual - saved) > 1e-3


@pytest.mark.parametrize("kind", ["state", "chunk", "missing", "scale", "shape"])
def test_damaged_model_and_coverage_refused(tmp_path, kind):
    packet, boundary = saved_fixture(tmp_path)
    if kind in ("state", "chunk"):
        entry = boundary["state"] if kind == "state" else boundary["chunks"][0]
        with (tmp_path / entry["path"]).open("ab") as stream:
            stream.write(b"changed")
    elif kind == "missing":
        boundary["chunks"].pop()
    elif kind == "scale":
        entry = boundary["chunks"][0]
        with np.load(tmp_path / entry["path"], allow_pickle=False) as arrays:
            data = {key: np.array(arrays[key]) for key in arrays.files}
        data["scale"] = np.array(0.0)
        atomic_npz(tmp_path / entry["path"], **data)
        entry["sha256"] = sha(tmp_path / entry["path"])
    else:
        entry = boundary["state"]
        atomic_npz(
            tmp_path / entry["path"],
            a=np.ones(3, dtype=np.complex128),
            c=np.ones(packet["active_rows"], dtype=np.complex128),
        )
        entry["sha256"] = sha(tmp_path / entry["path"])
    atomic_json(tmp_path / "committed.json", boundary)
    with pytest.raises(ValueError, match="FROZEN_"):
        rebuild_frozen_field(tmp_path, packet)


def test_actual_complex_writer_reopen(tmp_path):
    file = tmp_path / "actual_physics_types.json"
    atomic_json(
        file,
        dict(
            selected=np.array([[1.0 + 2j, -3j]]),
            scalar=np.float64(1e-14),
            qualified=np.bool_(False),
        ),
    )
    record = json.loads(file.read_text())
    assert record["qualified"] is False
    assert record["selected"][0][0] == dict(real=1.0, imag=2.0)
