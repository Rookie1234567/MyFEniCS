"""V29 pure startup/mapping/transaction fixtures; no native FE certificate."""

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from src.io.finite_json import atomic_json
from src.io.w1_evidence import file_receipt, seal_stage
from src.io.w1_surface_contract import validate_qualification, validate_surface_fields
from src.runners import w1_start_freshness as fresh
from src.runners.w1_admission_budget import update_budget
from src.runners.w1_surface_payload import commit_surface
from src.solvers.w1_full_surface_action import FullSurfaceAdapter
from src.solvers.w1_full_surface_saved import expected_maps, read_array, terms

ROOT = Path(__file__).resolve().parents[2]


def test_start_freshness_and_identity(tmp_path):
    window = tmp_path / "window.json"
    atomic_json(window, dict(fixed=True))
    spec = dict(input_sha256="d" * 64, window_path=str(window))
    issuer = dict(pid=123, start_ticks=987, uid=1000)
    grant = dict(
        schema="w1-worker-start-grant.v29",
        observed_after_cpu_monotonic=100.0,
        boot_id="boot",
        issuer=issuer,
        cpuset_cpus=[2, 3],
        selected_cpu=2,
        source_sha="a" * 40,
        input_sha256=spec["input_sha256"],
        window_sha256=fresh.digest(window),
        fresh_CPU_observation=True,
        PSI_qualification_is_separate=True,
    )
    options = dict(now=101.0, boot="boot", cpuset=[2, 3], issuer=issuer, affinity=[2])
    assert fresh.validate_grant(grant, spec, "a" * 40, **options)["age_seconds"] == 1.0
    for field, value in [
        ("now", 116.0),
        ("now", 99.0),
        ("boot", "other"),
        ("cpuset", [2]),
        ("issuer", dict(issuer, start_ticks=988)),
        ("affinity", [3]),
    ]:
        with pytest.raises(ValueError):
            fresh.validate_grant(
                grant, spec, "a" * 40, **dict(options, **{field: value})
            )
    with pytest.raises(ValueError):
        fresh.validate_grant(grant, spec, "b" * 40, **options)
    repaired = dict(grant, observed_after_cpu_monotonic=116.0)
    assert fresh.validate_grant(repaired, spec, "a" * 40, **dict(options, now=117.0))[
        "passed"
    ]
    atomic_json(window, dict(fixed=False))
    with pytest.raises(ValueError):
        fresh.validate_grant(repaired, spec, "a" * 40, **dict(options, now=117.0))


def test_last_grant_read_new_25_rejected(tmp_path):
    window = tmp_path / "window.json"
    atomic_json(window, dict(schema="task42extra.w1-v29-batch-window.v1"))
    atomic_json(
        tmp_path / "resource_samples.json",
        dict(events=[dict(kind="admission", elapsed_seconds=1.0) for _ in range(24)]),
    )
    assert len(update_budget(window)["events"]) == 24
    with pytest.raises(TimeoutError):
        update_budget(window, before_admission=True)


def fixed_spec():
    return dict(
        stage="surface_p4",
        surface_scope="original_2176_facets",
        degree=4,
        generic_seed=4212801,
        seam_seed=4212901,
        integration_profile="q60_native",
    )


def test_full_surface_contract_is_opt_in():
    validate_surface_fields(fixed_spec())
    for field, value in [
        ("surface_scope", "two_representatives"),
        ("degree", 6),
        ("generic_seed", 1),
        ("seam_seed", 4212902),
        ("integration_profile", "q80"),
        ("stage", "boundary"),
    ]:
        with pytest.raises(ValueError):
            validate_surface_fields(dict(fixed_spec(), **{field: value}))


def test_real_api_adapter_all_facets():
    calls = []

    class ActualInterfaceFixture:
        def __init__(self, layout, modes, q, *, face_inventory):
            calls.append(("init", q, face_inventory))
            self.face_inventory = face_inventory
            self.face_masks = None

        def project_components(self, t):
            calls.append("components")
            return t

        def recover(self, t):
            calls.append("recover")
            return t

        def apply(self, t, adjoint=False):
            calls.append("adjoint" if adjoint else "apply")
            return t

        def modal_rhs(self, a):
            calls.append("modal_rhs")
            return a

    state = dict(
        trace=np.array([1 + 2j]), dual=np.array([2 - 3j]), alpha=np.array([3 + 4j])
    )
    adapter = FullSurfaceAdapter(object(), [], action_class=ActualInterfaceFixture)
    values = adapter.evaluate(state)
    assert calls == [
        ("init", 60, None),
        "components",
        "recover",
        "apply",
        "adjoint",
        "modal_rhs",
    ]
    assert np.array_equal(values["adjoint"], state["dual"])
    # Class invocation routing only. Native qualified classes execute in P1.


def test_saved_array_damage_is_rejected(tmp_path):
    path = tmp_path / "a.npz"
    np.savez(path, a=np.array([1 + 2j, 3 - 4j]))
    row = file_receipt(path)
    row["path"] = "a.npz"
    assert (
        terms(read_array(tmp_path, row)["a"], np.array([1 + 2j, 3 - 4j]))["relative"]
        == 0
    )
    np.savez(path, a=np.array([1 + 3j, 3 - 4j]))
    with pytest.raises(ValueError):
        read_array(tmp_path, row)
    row = file_receipt(path)
    row["path"] = "a.npz"
    assert (
        terms(read_array(tmp_path, row)["a"], np.array([1 + 2j, 3 - 4j]))["relative"]
        > 1e-10
    )
    with pytest.raises(ValueError):
        terms([np.nan], [1.0])
    row["path"] = "../a.npz"
    with pytest.raises(ValueError):
        read_array(tmp_path, row)


def test_native_D_complex_polarization_conjugate():
    from src.solvers.w1_full_surface_saved import native_D_columns

    integral = np.array([[1 + 2j, 3 - 4j], [-2 + 0.5j, 0.3 - 1j]])
    electric = np.array([0.5 + 0.2j, -0.7 + 0.4j])
    expected = np.array([
        sum(integral[i, j] * electric[j] for j in range(2)).conjugate() / 1250
        for i in range(2)
    ])
    np.testing.assert_allclose(native_D_columns(integral, electric, 1250), expected, rtol=1e-14, atol=0)
    assert not np.allclose(integral.conj() @ electric / 1250, expected)


def test_original_manifest_without_derived_reference_plane():
    from src.solvers.w1_full_surface_saved import physical_reference_planes

    assert np.array_equal(physical_reference_planes([{"side": "top"}, {"side": "bottom"}]), [130., -10.])
    with pytest.raises(ValueError):
        physical_reference_planes([{"side": "top", "reference_plane_nm": 0.}])


def test_native_vector_denominator_matches_accepted_contract():
    from src.solvers.w1_full_surface_saved import metric_verdict
    from src.solvers.w1_saved_boundary import terms as accepted_terms

    reference = np.array([1.+2j, 2e-17+1e-18j])
    candidate = reference + np.array([1e-14, 5e-16])
    original = terms(candidate, reference)
    assert abs(original["relative"] - accepted_terms(candidate, reference)["relative"]) < 1e-25
    assert metric_verdict(original["relative"]) == (True, False)
    tiny_column = terms(candidate[1], reference[1])
    assert metric_verdict(tiny_column["relative"], "additional_column_diagnostic") == (False, False)
    assert metric_verdict(tiny_column["relative"]) == (False, True)
    with pytest.raises(ValueError):
        metric_verdict(1., "ignore_failure")


def test_relative_package_loader_has_fixed_instance_gate():
    from src.runners.w1_surface_payload import PACKAGE_LOADER

    compile(PACKAGE_LOADER, "consumer.py", "exec")
    assert "PACKAGE_QUALIFIED_MODE_IDENTITY" in PACKAGE_LOADER
    assert "c354afa449fb80cfb5012e7d2ff66a3e3e64e088" in PACKAGE_LOADER


def test_qualification_lifecycle_groups_only_fixed_roots():
    from src.io.w1_surface_contract import lifecycle_case, lifecycle_count

    spec = {"component": "original_size_full_surface_w1"}
    entries = [dict(stage="input_contract_checks", output="/own/"+name+"/input_contract_checks") for name in ("a29","a129","a229")]
    case = lifecycle_case(spec, "/own/a429", "input_contract_checks")
    assert lifecycle_count(spec, entries, case) == 0
    entries += [dict(stage="input_contract_checks", output="/own/"+name+"/input_contract_checks") for name in ("a329","a429","a529")]
    assert lifecycle_count(spec, entries, case) == 3
    with pytest.raises(ValueError):
        lifecycle_case(spec, "/own/unlimited_new_source", "input_contract_checks")
    assert lifecycle_case(spec, "/own/p429", "surface_p4") == "surface_p4"


def small_geometry():
    vertices = np.array(
        [[i, j, k] for k in (0, 1) for j in (0, 1) for i in (0, 1)], float
    )
    edges = np.array(
        [
            [0, 1],
            [0, 2],
            [0, 4],
            [1, 3],
            [1, 5],
            [2, 3],
            [2, 6],
            [3, 7],
            [4, 5],
            [4, 6],
            [5, 7],
            [6, 7],
        ]
    )
    return dict(
        degree=np.array(1),
        x=np.array([-1.0, 0.0, 1.0]),
        y=np.array([-1.0, 0.0, 1.0]),
        edge_dofs=np.arange(12)[:, None],
        face_dofs=np.empty((6, 0), int),
        element_geometry=vertices,
        edge_vertices=edges,
        phases=np.array([np.exp(0.3j), np.exp(-0.7j)]),
        bottom_active=np.array([0, 1, 3, 5]),
        top_active=np.array([8, 9, 10, 11]),
    )


def test_periodic_geometry_mapping():
    data = small_geometry()
    mapping = expected_maps(data)
    assert (
        len(np.unique(np.concatenate([m.ravel() for m, w in mapping.values()]))) == 16
    )
    for side, (m, w) in mapping.items():
        # Opposite periodic edges share one representative, with one phase.
        assert m[1, 0, 2] == m[0, 0, 1] and w[1, 0, 2] == data["phases"][0]
        assert m[0, 1, 3] == m[0, 0, 0] and w[0, 1, 3] == data["phases"][1]
        assert w[1, 1, 2] == data["phases"][0] and w[1, 1, 3] == data["phases"][1]
    bad = copy.deepcopy(data)
    bad["face_dofs"] = np.zeros((6, 1), int)
    with pytest.raises((ValueError, KeyError)):
        expected_maps(bad)


@pytest.mark.parametrize("failure", ["NONE", "SUPERVISION", "STALE"])
def test_actual_writer_seal_reopen_consumer(tmp_path, monkeypatch, failure):
    from src.test.test_w1_versioned_input import transaction_fixture
    from src.io.w1_evidence import scientific_identity, validate_stage

    run, spec = transaction_fixture(tmp_path, monkeypatch)
    binding = json.loads((run / "binding.json").read_text())
    binding["stage"] = "input_contract_checks"
    atomic_json(run / "binding.json", binding)
    spec.update(
        stage="input_contract_checks",
        A_qualification_path=str(tmp_path / "qualification.json"),
    )
    raw = run / "junit.xml"
    names = [
        "test_start_freshness_and_identity",
        "test_last_grant_read_new_25_rejected",
        "test_full_surface_contract_is_opt_in",
        "test_real_api_adapter_all_facets",
        "test_saved_array_damage_is_rejected",
        "test_periodic_geometry_mapping",
    ]
    raw.write_text(
        "<testsuite>"
        + "".join('<testcase name="' + n + '"/>' for n in names)
        + "</testsuite>"
    )
    atomic_json(
        run / "component_result.json",
        dict(
            status="V29_SURFACE_CONTRACT_TESTS_PASS",
            raw=file_receipt(raw),
            receiver_source_sha="a" * 40,
            binding_sha256=fresh.digest(run / "binding.json"),
        ),
    )
    atomic_json(
        run / "worker_start_freshness.json",
        dict(passed=True, age_seconds=16.0 if failure == "STALE" else 1.0),
    )
    summary = json.loads((run / "supervisor_summary.json").read_text())
    summary["rss_hard_limit_bytes"] = 2 * 2**30
    if failure == "SUPERVISION":
        summary["classification"] = "RESOURCE_WINDOW_UNAVAILABLE"
    atomic_json(run / "supervisor_summary.json", summary)
    atomic_json(run / "evidence.json", seal_stage(run))
    receiver = json.loads((run / "receiver_result.json").read_text())
    receiver.update(
        evidence_sha256=fresh.digest(run / "evidence.json"),
        binding_sha256=fresh.digest(run / "binding.json"),
    )
    atomic_json(run / "receiver_result.json", receiver)
    if failure != "NONE":
        with pytest.raises(ValueError):
            commit_surface(run, spec, receiver, [])
        assert not Path(spec["A_qualification_path"]).exists()
    else:
        commit_surface(run, spec, receiver, [])
        assert (
            validate_qualification(spec["A_qualification_path"], {})["scope"]
            == "PURE_FULL_SURFACE_STARTUP_DELTA"
        )
        validate_stage(
            run,
            identity=scientific_identity(binding),
            statuses={"V29_SURFACE_CONTRACT_TESTS_PASS"},
        )


def test_bootstrap_does_not_pin_current_numerical_namespace():
    import subprocess
    import sys

    command = """import importlib.util,sys
from pathlib import Path
p=Path('src/runners/w1_start_freshness.py')
s=importlib.util.spec_from_file_location('_test_bootstrap',p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
assert m.current_cpuset()
assert 'src' not in sys.modules and 'benchmarks' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", command], cwd=ROOT, check=True)
