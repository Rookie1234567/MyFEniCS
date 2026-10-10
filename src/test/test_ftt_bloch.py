"""Small independent phase, complete-moment, complex derivative and use tests."""

from copy import deepcopy
import json
import numpy as np
import pytest
import torch

from src.solvers.ftt_field import FTTField
from src.solvers.ftt_bloch_field import BlochFTTField, IndependentPointPhase, scalar_continuation
from src.solvers.ftt_factored_moments import FactoredMomentMap, model_identity
from src.solvers.ftt_moments import StreamingMomentMap
from src.solvers.ftt_conditional_core import ConditionalCoreAction, output_coefficients, set_output_coefficients
from src.test.test_ftt_structure import fixture, BOX
from src.test.test_ftt_conditional_core import TinyAction


def phase(k=(1.1, -0.8, 0.0)):
    return dict(wavevector_nm_inverse=list(k), origin_nm=[0.13, -0.21, 0.0],
        coordinate_unit="physical_nm", sign=1, unfolded_incident_wavevector=True,
        mode_manifest_sha256="a" * 64)


@pytest.mark.parametrize("kind", ["fttnn", "chebtt"])
@pytest.mark.parametrize("geometry", ["box", "permuted", "skew"])
def test_explicit_physical_phase_all_moments_and_adjoint(kind, geometry):
    p = fixture(geometry == "permuted", geometry == "skew")
    model = BlochFTTField(BOX, kind, phase())
    model.nonzero_qualification_state()
    exact = IndependentPointPhase(model)
    old, new = StreamingMomentMap(p, 128), FactoredMomentMap(p)
    np.testing.assert_allclose(new.forward(model, 8), old.forward(exact, 1), rtol=1e-11, atol=1e-14)
    dual = np.arange(1, 7).astype(np.complex128) * (0.8 + 0.7j)
    np.testing.assert_allclose(new.vjp(model, dual, 8), old.vjp(exact, dual, 1), rtol=1e-10, atol=1e-12)
    # The skew path really invokes the independent complete point fallback.
    if geometry == "skew":
        assert all(not row["aligned"] for row in new.geometry_records)


@pytest.mark.parametrize("kind", ["fttnn", "chebtt"])
@pytest.mark.parametrize("axis", [0, 1, 2])
def test_bloch_active_core_not_overwritten_and_complex_adjoint(kind, axis):
    rng = np.random.default_rng(4214201)
    model = BlochFTTField(BOX, kind, phase())
    model.nonzero_qualification_state()
    mapping = FactoredMomentMap(fixture(skew=True))
    action = TinyAction(rng.normal(size=(6, 6)) + 1j * rng.normal(size=(6, 6)))
    op = ConditionalCoreAction(model, mapping, action, axis)
    base = deepcopy(model.state_dict())
    c = mapping.forward(model)
    d = (rng.normal(size=op.size) + 1j * rng.normal(size=op.size)).astype(np.complex128)
    v = (rng.normal(size=6) + 1j * rng.normal(size=6)).astype(np.complex128)
    Kd = op.K(d)
    np.testing.assert_allclose(np.vdot(Kd, v), np.vdot(d, op.KH(v)), rtol=1e-10, atol=1e-12)
    np.testing.assert_allclose(np.vdot(op.B(d), v), np.vdot(d, op.BH(v)), rtol=1e-10, atol=1e-12)
    w = output_coefficients(model, axis)
    set_output_coefficients(model, axis, w + d.reshape(op.shape))
    mapping.invalidate()
    np.testing.assert_allclose(mapping.forward(model), c + Kd, rtol=1e-10, atol=1e-13)
    model.load_state_dict(base)
    np.testing.assert_allclose(mapping.forward(model), c, rtol=0, atol=0)


@pytest.mark.parametrize("kind", ["fttnn", "chebtt"])
def test_zero_phase_c_vjp_active_update_and_initial_identity(kind):
    plain, bloch = FTTField(BOX, kind), BlochFTTField(BOX, kind, phase((0, 0, 0)))
    assert sum(p.numel() for p in bloch.parameters()) == (9072 if kind == "fttnn" else 9120)
    for (n, p), (nn, q) in zip(plain.named_parameters(), bloch.named_parameters(), strict=True):
        assert n == nn and torch.equal(p, q)
    mapping = FactoredMomentMap(fixture())
    assert not np.any(mapping.forward(bloch))
    for m in (plain, bloch):
        m.nonzero_qualification_state()
    np.testing.assert_allclose(mapping.forward(plain), mapping.forward(bloch), rtol=0, atol=0)
    dual = np.arange(6).astype(np.complex128) + 0.4j
    np.testing.assert_allclose(mapping.vjp(plain, dual), mapping.vjp(bloch, dual), rtol=0, atol=0)


@pytest.mark.parametrize("kind", ["fttnn", "chebtt"])
def test_zero_phase_one_complete_core_update(kind):
    from src.solvers.ftt_conditional_core import solve_core, verify_and_apply_core
    plain, bloch = FTTField(BOX, kind), BlochFTTField(BOX, kind, phase((0, 0, 0)))
    mapping = FactoredMomentMap(fixture())
    rng = np.random.default_rng(4214201)
    action = TinyAction((rng.normal(size=(6, 6)) + 1j * rng.normal(size=(6, 6))).astype(np.complex128))
    updates = []
    for model in (plain, bloch):
        model.nonzero_qualification_state()
        c = mapping.forward(model)
        op = ConditionalCoreAction(model, mapping, action, 2)
        delta, _ = solve_core(op, (action.f - action.apply(c)) / action.bnorm, maxiter=10)
        c, r, accepted = verify_and_apply_core(model, mapping, action, op, delta, c)
        assert accepted["accepted"]
        updates.append((c, r, delta))
    for left, right in zip(*updates, strict=True):
        np.testing.assert_allclose(left, right, rtol=1e-10, atol=1e-13)


def test_synthetic_two_nonunit_floquet_seams_corner_and_negative_sign_units_fold():
    phase_data = phase()
    m = BlochFTTField(BOX, "fttnn", phase_data)
    # Constant complex envelope in each axis avoids assuming a random FTT is periodic.
    for axis in range(3):
        coeff = np.zeros_like(output_coefficients(m, axis))
        coeff[-1, :, 0, 0] = 1 + 0.2j
        set_output_coefficients(m, axis, coeff)
    points = torch.tensor([[-2., -2., .3], [2., -2., .3], [-2., 2., .3], [2., 2., .3]], dtype=torch.float64)
    value = m(points).detach().numpy()
    fx, fy = np.exp(4j * 1.1), np.exp(-4j * 0.8)
    assert abs(fx - 1) > 0.1 and abs(fy - 1) > 0.1
    np.testing.assert_allclose(value[1], fx * value[0], rtol=1e-12)
    np.testing.assert_allclose(value[2], fy * value[0], rtol=1e-12)
    np.testing.assert_allclose(value[3], fx * fy * value[0], rtol=1e-12)
    from src.solvers.ftt_bloch_qualification import WrongPointPhase
    for wrong in ("wrong_sign", "wrong_units", "folded_kx"):
        bad = WrongPointPhase(m, wrong)(points).detach().numpy()
        assert np.linalg.norm(bad - value) / np.linalg.norm(value) > 0.01
    assert np.linalg.norm(fx**2 * value[0] - value[1]) > 0.01  # repeated MPC phase


def test_phase_buffers_cache_restore_and_checkpoint_reopen(tmp_path):
    from src.solvers.optimization_checkpoint import capture, restore, atomic_write, load_checkpoint
    from src.io.neural_wave_campaign import digest
    m = BlochFTTField(BOX, "fttnn", phase())
    m.nonzero_qualification_state()
    optimizer = torch.optim.Adam(m.parameters())
    state = capture(m, optimizer, {"production_initialization_allowed": False})
    mapping = FactoredMomentMap(fixture())
    oldc, identity = mapping.forward(m), model_identity(m)
    with torch.no_grad():
        m.phase_wavevector[1].add_(0.1)
    assert model_identity(m) != identity and np.linalg.norm(mapping.forward(m) - oldc) > 0
    restore(m, optimizer, state)
    np.testing.assert_allclose(mapping.forward(m), oldc, atol=0, rtol=0)
    path = tmp_path / "committed.pt"
    atomic_write(path, lambda stream: torch.save(state, stream))
    saved = load_checkpoint(path, digest(path))
    assert not saved["metadata"]["production_initialization_allowed"]
    assert all(torch.equal(saved["model"][key], m.state_dict()[key]) for key in m.phase_buffer_names)


def test_fixed_scalar_rules_and_reference_vector_negative_control(tmp_path):
    from src.solvers.ftt_bloch_field import scalar_checkpoint_pending
    assert scalar_checkpoint_pending({"complete_rounds": 2}, [{"native": .6}])
    assert not scalar_checkpoint_pending({"complete_rounds": 2}, [{"isolated_validation_scalars": {}}])
    assert not scalar_checkpoint_pending({"complete_rounds": 3}, [{"native": .6}])
    assert not scalar_continuation(2, .6, .7, .8)
    assert scalar_continuation(2, .6, .4, .8)
    assert scalar_continuation(4, .07, .09, .09, .1)
    assert scalar_continuation(4, .09, .15, .15, .2)
    assert not scalar_continuation(4, .11, .15, .15, .2)
    from src.postprocessing.ftt_bloch_scalars import read_scalars
    request = dict(round=2, boundary_sha256="b", field_sha256="c", source_sha="d", design_sha256="e")
    value = dict(request, schema="ftt.bloch-validation.scalars.v1", native_relative=.6, augmented_relative=.6,
        scattered_E_relative=.7, scattered_H_relative=.8, scattered_curl_relative=.8,
        reference_feedback="scalars_only", production_initialization_allowed=False)
    path = tmp_path / "scalars.json"
    path.write_text(json.dumps(value))
    assert read_scalars(path, request) == value
    for extra in ({"reference_vector": [1, 2]}, {"boundary_sha256": "wrong"}, {"production_initialization_allowed": True}):
        path.write_text(json.dumps(dict(value, **extra)))
        with pytest.raises(ValueError):
            read_scalars(path, request)


def test_new_version_stages_and_numeric_resource_registration():
    from src.io.neural_wave_campaign import ROOT, load_wave, profile_paths
    from src.io.ftt_bloch_campaign import STAGES
    from src.runners.neural_wave_campaign import window
    for stage in STAGES:
        spec = load_wave(ROOT / ("input/task042extra_feinn_5nm/" + stage + ".dat"))
        assert spec["campaign_version"] == 42 and spec["max_seconds"] <= 5400
        assert profile_paths(spec)["root"].name == "v42"
        assert window(spec)["budget_s"] == 28800
