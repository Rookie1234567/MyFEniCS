"""Independent complex chain/QR/atomic-boundary checks for the V30 opt-in."""

import json

import numpy as np
import pytest
from scipy import linalg

from src.solvers.neural_wave_moments import (
    Patch,
    WaveMoments,
    pack,
    unpack,
    score_and_cotangent,
)
from src.solvers.neural_wave_subspace import WaveSubspace
from src.solvers.neural_wave_greedy import (
    BasisStore,
    atomic_npz,
    sha,
    variable_projection,
)
from src.io.neural_wave_campaign import ROOT, training_open_allowed


class Action:
    def __init__(self, matrix, f):
        self.matrix, self.f = matrix, f
        self.size = len(f)
        self.bnorm = float(np.linalg.norm(f))

    def apply(self, c, adjoint=False):
        return (self.matrix.conj().T if adjoint else self.matrix) @ c


def fixture():
    rng = np.random.default_rng(4213001)
    points = rng.uniform(0.05, 0.95, (11, 3))
    interpolation = rng.normal(size=(9, 33))
    transform = np.eye(9)[[2, 0, 1, 5, 3, 4, 8, 6, 7]]
    transform[1] *= -1
    packet = dict(
        quadrature_degree=30,
        reference_points=points,
        interpolation=interpolation,
        transforms=np.array([np.eye(9), transform]),
        orientation_ids=np.array([0, 1]),
        owner_rows=np.arange(18).reshape(2, 9),
        active_rows=18,
        origins=np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        jacobians=np.array(
            [
                np.diag([1.0, 1.3, 0.7]),
                [[1.0, 0.2, 0.0], [0.0, 1.3, 0.0], [0.0, 0.0, 0.7]],
            ]
        ),
    )
    matrix = rng.normal(size=(18, 18)) + 1j * rng.normal(size=(18, 18))
    f = rng.normal(size=18) + 1j * rng.normal(size=18)
    return rng, packet, Action(matrix, f)


def direct(packet, patch, q, p):
    c = np.zeros(int(packet["active_rows"]), complex)
    for cell, jac in enumerate(packet["jacobians"]):
        x = packet["origins"][cell] + packet["reference_points"] @ jac.T
        v = patch.window(x)[:, None] * (np.exp(1j * (x - patch.center) @ q.T) @ p)
        local = packet["interpolation"] @ (v @ jac).T.ravel()
        local = packet["transforms"][packet["orientation_ids"][cell]] @ local
        c[packet["owner_rows"][cell]] = local
    return c


def tensor_fixture():
    """Independent weighted polynomial densities on all 12/6/1 entities."""
    from itertools import product

    rng = np.random.default_rng(4213004)
    t, w = np.polynomial.legendre.leggauss(4)
    t, w = (t + 1) / 2, w / 2
    points, blocks = [], []
    next_row = 0
    for code in product((-1, 0, 1), repeat=3):
        axes = np.flatnonzero(np.array(code) == -1)
        d = len(axes)
        if not d:
            continue
        idx = np.array(list(product(range(4), repeat=d)))
        pts = np.tile(code, (len(idx), 1)).astype(float)
        pts[:, axes] = t[idx]
        weight = np.prod(w[idx], axis=1)
        powers = np.array(list(product(range(4), repeat=d)))
        table = np.ones((len(idx), len(powers)))
        for j, axis in enumerate(axes):
            table *= np.polynomial.legendre.legvander(2 * pts[:, axis] - 1, 3)[
                :, powers[:, j]
            ]
        count = (3, 12, 36)[d - 1]
        coefficient = rng.normal(size=(count, 3, len(powers)))
        block = np.zeros((144, 3, len(idx)))
        block[next_row : next_row + count] = (coefficient @ table.T) * weight
        next_row += count
        points.append(pts)
        blocks.append(block)
    assert next_row == 144
    points = np.vstack(points)
    interpolation = np.concatenate(blocks, axis=2).reshape(144, -1)
    perm = np.arange(144)[::-1]
    transform = np.eye(144)[perm]
    transform[::3] *= -1
    packet = dict(
        reference_points=points,
        interpolation=interpolation,
        origins=np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        jacobians=np.array(
            [
                np.diag([1.0, 1.3, 0.7]),
                [[0.0, 1.0, 0.0], [1.3, 0.0, 0.0], [0.0, 0.0, -0.7]],
            ]
        ),
        transforms=np.array([np.eye(144), transform]),
        orientation_ids=np.array([0, 1]),
        owner_rows=np.arange(288).reshape(2, 144),
        active_rows=288,
        quadrature_degree=7,
    )
    return rng, packet


def test_factorized_all_entity_moments_and_real_adjoint():
    from src.solvers.neural_wave_factorized import FactorizedWaveMoments

    rng, packet = tensor_fixture()
    patch = Patch((0.8, 0.5, 0.2), (2.0, 1.8, 1.5))
    q = rng.normal(size=(2, 3))
    p = rng.normal(size=(2, 3)) + 1j * rng.normal(size=(2, 3))
    g = rng.normal(size=288) + 1j * rng.normal(size=288)
    original, fast = WaveMoments(packet), FactorizedWaveMoments(packet)
    np.testing.assert_allclose(
        fast.forward(patch, q, p), direct(packet, patch, q, p), rtol=1e-10, atol=1e-11
    )
    expected, actual = original.vjp(patch, q, p, g), fast.vjp(patch, q, p, g)
    for e, a in zip(expected, actual, strict=True):
        np.testing.assert_allclose(a, e, rtol=1e-10, atol=1e-11)
    np.testing.assert_allclose(
        fast.forward(patch, q, p),
        FactorizedWaveMoments(packet, 1).forward(patch, q, p),
        rtol=0,
        atol=0,
    )
    theta, v = pack(q, p), rng.normal(size=18)
    v /= np.linalg.norm(v)
    step = 1e-5
    finite = np.vdot(
        g,
        fast.forward(patch, *unpack(theta + step * v))
        - fast.forward(patch, *unpack(theta - step * v)),
    ).real / (2 * step)
    assert abs(finite - pack(*actual) @ v) <= 1e-7 * max(1, abs(finite))
    assert fast.density_pair_relative < 1e-12
    assert fast.maximum_window_coordinate_defect_nm == 0


def test_original_pointwise_accepted_map():
    from src.solvers.neural_wave_reconstruction import pointwise_moments

    rng, packet, _ = fixture()
    patch = Patch((0.8, 0.5, 0.3), (2.0, 1.0, 1.0))
    q = rng.normal(size=(2, 3))
    p = rng.normal(size=(2, 3)) + 1j * rng.normal(size=(2, 3))
    actual = pointwise_moments(
        packet,
        lambda x: patch.window(x)[:, None]
        * (np.exp(1j * (x - patch.center) @ q.T) @ p),
    )
    np.testing.assert_allclose(
        actual, direct(packet, patch, q, p), rtol=1e-12, atol=1e-12
    )
    supported = pointwise_moments(
        packet,
        lambda x: patch.window(x)[:, None]
        * (np.exp(1j * (x - patch.center) @ q.T) @ p),
        zero_outside_patch=patch,
    )
    np.testing.assert_array_equal(supported, actual)


def test_factorization_rejects_unproved_geometry_and_density():
    from src.solvers.neural_wave_factorized import FactorizedWaveMoments

    _, packet = tensor_fixture()
    packet["jacobians"][0, 0, 1] = 0.1
    with pytest.raises(ValueError, match="Cartesian geometry proof failed"):
        FactorizedWaveMoments(packet)
    _, packet = tensor_fixture()
    packet["interpolation"][0, 0] += 1
    with pytest.raises(ValueError, match="polynomial density compression failed"):
        FactorizedWaveMoments(packet, degree=2)


def test_full_complex_forward_and_real_vjp():
    rng, packet, _ = fixture()
    patch = Patch((0.8, 0.5, 0.3), (2.0, 1.0, 1.0))
    q = rng.normal(size=(2, 3))
    p = rng.normal(size=(2, 3)) + 1j * rng.normal(size=(2, 3))
    g = rng.normal(size=18) + 1j * rng.normal(size=18)
    m = WaveMoments(packet, 8)
    np.testing.assert_allclose(
        m.forward(patch, q, p), direct(packet, patch, q, p), atol=1e-12, rtol=1e-12
    )
    np.testing.assert_allclose(
        m.forward(patch, q, p),
        WaveMoments(packet, 1).forward(patch, q, p),
        atol=1e-12,
        rtol=1e-12,
    )
    gq, gp = m.vjp(patch, q, p, g)
    gradient = pack(gq, gp)
    theta = pack(q, p)
    v = rng.normal(size=len(theta))
    v /= np.linalg.norm(v)

    def fun(t):
        return np.vdot(g, direct(packet, patch, *unpack(t))).real

    derivative = (fun(theta + 1e-5 * v) - fun(theta - 1e-5 * v)) / 2e-5
    assert abs(derivative - gradient @ v) < 1e-8 * max(1, abs(derivative))


def test_score_envelope_gradient_independently():
    rng, packet, action = fixture()
    space = WaveSubspace(action, 8)
    for _ in range(3):
        space.add(rng.normal(size=18) + 1j * rng.normal(size=18))
    moments = WaveMoments(packet)
    patch = Patch((0.8, 0.5, 0.3), (2.0, 1.0, 1.0))
    q = rng.normal(size=(2, 3))
    value = variable_projection(action, space, moments, patch, q, gradient=True)
    v = rng.normal(size=q.shape)
    v /= np.linalg.norm(v)

    def objective(w):
        return (
            variable_projection(action, space, moments, patch, w, gradient=False)[0]
            / action.bnorm**2
        )

    finite = (objective(q + 1e-5 * v) - objective(q - 1e-5 * v)) / 2e-5
    assert abs(finite - np.sum(value[-1] * v)) < 1e-7
    z = rng.normal(size=18) + 1j * rng.normal(size=18)
    dz = rng.normal(size=18) + 1j * rng.normal(size=18)
    _, gz = score_and_cotangent(z, action.f)
    finite = (
        score_and_cotangent(z + 1e-6 * dz, action.f)[0]
        - score_and_cotangent(z - 1e-6 * dz, action.f)[0]
    ) / 2e-6
    assert abs(finite - np.vdot(gz, dz).real) < 1e-7


def test_nonhermitian_incremental_qr_against_independent_svd():
    rng, _, action = fixture()
    space = WaveSubspace(action, 12)
    columns = rng.normal(size=(18, 10)) + 1j * rng.normal(size=(18, 10))
    for j in range(10):
        event = space.add(columns[:, j] * 10.0 ** (j - 5))
        assert event["accepted"]
        a = linalg.lstsq(
            action.matrix @ columns[:, : j + 1],
            action.f,
            cond=1e-12,
            lapack_driver="gelsd",
        )[0]
        expected = action.f - action.matrix @ columns[:, : j + 1] @ a
        np.testing.assert_allclose(space.r, expected, atol=1e-11, rtol=1e-11)
    assert not space.add(columns[:, 0])["accepted"]
    assert not space.add(columns[:, 0] + 1e-14 * columns[:, 1])["accepted"]
    assert space.rank_audit()["orthogonality"] < 1e-12


def test_atomic_complete_boundary_reopen_and_corruption(tmp_path):
    rng, _, action = fixture()
    space = WaveSubspace(action, 3)
    store = BasisStore(tmp_path, dict(source_sha="a" * 40))
    event = space.add(rng.normal(size=18) + 1j * rng.normal(size=18))
    model = dict(
        patch=Patch((0, 0, 0), (1, 1, 1)), q=np.ones((1, 3)), p=np.ones((1, 3), complex)
    )
    value = store.commit(space, model, 1, event, rng, 1e20)
    saved = json.loads((tmp_path / "committed.json").read_text())
    assert saved["state"]["sha256"] == sha(tmp_path / value["state"]["path"])
    restored = WaveSubspace(action, 3)
    BasisStore(tmp_path, dict(source_sha="b" * 40)).restore(restored, rng)
    np.testing.assert_array_equal(restored.c, space.c)
    np.testing.assert_array_equal(restored.r, space.r)
    # Interrupted temp data never replaces the complete published boundary.
    (tmp_path / "committed.json.tmp").write_text("{")
    assert json.loads((tmp_path / "committed.json").read_text())["committed"]
    with pytest.raises(ValueError, match="IMMUTABLE"):
        store.commit(space, model, 1, event, rng, 1e20)
    atomic_npz(tmp_path / value["state"]["path"], c=np.ones(18))
    assert sha(tmp_path / value["state"]["path"]) != saved["state"]["sha256"]
    with pytest.raises(ValueError, match="RECOVERY_STATE_HASH"):
        BasisStore(tmp_path, dict(source_sha="a" * 40)).restore(
            WaveSubspace(action, 3), rng
        )


def test_zero_direction_rejected():
    with pytest.raises(ValueError, match="DEGENERATE"):
        score_and_cotangent(np.zeros(2), np.ones(2))


def test_labels_gram_and_old_weights_excluded():
    design = dict(
        files={
            k: dict(path="benchmarks/artifacts/task42extra/data/" + k + ".npz")
            for k in ("native", "moments_q15", "moments_q30")
        }
    )
    assert training_open_allowed(ROOT / design["files"]["native"]["path"], design)
    for file in ("reference_state.npz", "gram.npz", "teacher.pt", "supervised.pth"):
        assert not training_open_allowed(
            ROOT / "benchmarks/artifacts/task42extra/data" / file, design
        )
    assert training_open_allowed(
        ROOT / "benchmarks/artifacts/task42extra/v30/x/basis/basis_00001.npz", design
    )


def test_torch_ad_is_independent_of_analytic_vjp():
    torch = pytest.importorskip("torch")
    torch.set_num_threads(1)
    rng, packet, _ = fixture()
    patch = Patch((0.8, 0.5, 0.3), (2.0, 1.0, 1.0))
    q = rng.normal(size=(2, 3))
    p = rng.normal(size=(2, 3)) + 1j * rng.normal(size=(2, 3))
    g = rng.normal(size=18) + 1j * rng.normal(size=18)
    theta = torch.tensor(pack(q, p), dtype=torch.float64, requires_grad=True)
    qt = theta[:6].reshape(2, 3)
    pt = torch.complex(theta[6:12], theta[12:]).reshape(2, 3)
    fields = []
    for cell, jac in enumerate(packet["jacobians"]):
        x = packet["origins"][cell] + packet["reference_points"] @ jac.T
        v = torch.tensor(patch.window(x))[:, None] * (
            torch.exp(1j * (torch.tensor(x - patch.center) @ qt.T)) @ pt
        )
        matrix = (
            packet["transforms"][packet["orientation_ids"][cell]]
            @ packet["interpolation"]
        )
        fields.append(
            torch.tensor(matrix, dtype=torch.complex128)
            @ (v @ torch.tensor(jac, dtype=torch.complex128)).T.ravel()
        )
    c = torch.cat(fields)
    objective = torch.vdot(torch.tensor(g), c).real
    objective.backward()
    qg, pg = WaveMoments(packet).vjp(patch, q, p, g)
    np.testing.assert_allclose(theta.grad.numpy(), pack(qg, pg), atol=1e-10, rtol=1e-10)


def test_actual_network_rebuild_from_frozen_parameters(tmp_path):
    from src.solvers.neural_wave_reconstruction import rebuild

    rng, packet, action = fixture()
    space = WaveSubspace(action, 4)
    moments = WaveMoments(packet)
    store = BasisStore(tmp_path, dict(source_sha="c" * 40))
    for i in range(3):
        patch = Patch((0.7 + i * 0.1, 0.5, 0.3), (2.0, 1.0, 1.0))
        q = rng.normal(size=(2, 3))
        p = rng.normal(size=(2, 3)) + 1j * rng.normal(size=(2, 3))
        event = space.add(moments.forward(patch, q, p))
        assert event["accepted"]
        store.commit(space, dict(patch=patch, q=q, p=p), i + 1, event, rng, 1e20)
    actual, saved, _ = rebuild(tmp_path, packet)
    np.testing.assert_allclose(actual, saved, atol=1e-11, rtol=1e-11)


def test_atomic_replace_interruption_preserves_published_state(tmp_path, monkeypatch):
    import os

    file = tmp_path / "state.npz"
    atomic_npz(file, c=np.arange(5))
    before = sha(file)

    def interrupted(*args):
        raise OSError("controlled interruption before replace")

    monkeypatch.setattr(os, "replace", interrupted)
    with pytest.raises(OSError, match="controlled interruption"):
        atomic_npz(file, c=np.arange(8))
    assert sha(file) == before


def test_explicit_stage_schema_and_ordinary_dispatch(tmp_path):
    from src.io.neural_wave_campaign import DESIGN, load_wave, digest
    from src.io.input_loader import InputError

    ordinary = tmp_path / "ordinary.dat"
    ordinary.write_text('schema_version = 1\n[model]\nname = "ordinary"\n')
    assert load_wave(ordinary) is None
    good = tmp_path / "wave.dat"
    good.write_text(
        'schema_version = 1\n[neural_wave]\nstage = "v30_m5_fixed_wave"\n'
        'design_sha256 = "' + digest(DESIGN) + '"\nreference_state = "teacher.npz"\n'
    )
    with pytest.raises(InputError, match="unknown/missing"):
        load_wave(good)
