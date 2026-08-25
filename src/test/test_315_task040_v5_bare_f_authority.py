from __future__ import annotations

import hashlib
import inspect
import json
import copy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import benchmarks.task040_level_a as level_a
import benchmarks.task040_level_a_watchdog as watchdog
import src.coupling.hybrid_one_cell_exact_traction_builder as one_cell_builder
import src.solvers.hybrid_bare_f_authority as authority
from src.coupling.hybrid_one_cell_exact_traction_builder import (
    select_negative_bottom_backward_column,
)


def test_operator_semantics_audit_separates_old_and_current_sources(
    tmp_path: Path,
) -> None:
    audit = authority.build_v5_operator_semantics_audit(
        source_sha="a" * 40,
        provenance={"observed": {"input_sha256": "b" * 64}},
    )
    assert (
        audit["old_rhs_source_definitions"]["modal_traction_positive"]["source"]
        == "setup.coupling.bottom.positive_traction"
    )
    assert (
        audit["old_rhs_source_definitions"]["modal_traction_negative"][
            "internal_traction_model"
        ]
        == "full3d_one_cell_exact_schur"
    )
    assert (
        audit["old_rhs_source_definitions"]["external_dtn_coupling"]["source"]
        == "pre_action_components.C"
    )
    assert (
        audit["current_rhs_source_definitions"]["external_dtn_coupling"]["source"]
        == "current_external_minimal_surface_components"
    )
    assert audit["modal_source_identity"]["pass"] is True
    assert audit["modal_source_identity"]["current_model"] == (
        "full3d_one_cell_exact_schur"
    )
    assert audit["modal_source_identity"]["repair"]["columns"] == [281, 283]
    assert audit["modal_source_identity"]["repair"]["scalar_cg_substitution"] is False
    assert audit["current_authority"]["authority_qualified"] == (
        "conditional_static_source_path"
    )
    assert audit["current_authority"]["runtime_qualification_required"] is True
    assert all(
        len(binding["file_sha256"]) == 64
        for binding in audit["evidence_bindings"].values()
    )

    audit_path = tmp_path / "operator_semantics_audit.json"
    audit_path.write_text(
        json.dumps(audit, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    assert hashlib.sha256(audit_path.read_bytes()).hexdigest() != audit["record_sha256"]


def test_operator_semantics_audit_writer_records_actual_file_sha(
    tmp_path: Path,
) -> None:
    audit = authority.build_v5_operator_semantics_audit(
        source_sha="a" * 40,
        provenance={},
    )
    binding = level_a._v5_write_operator_semantics_audit(MPI.COMM_SELF, tmp_path, audit)
    assert binding is not None
    audit_path = tmp_path / "operator_semantics_audit.json"
    assert binding["sha256"] == hashlib.sha256(audit_path.read_bytes()).hexdigest()
    assert binding["content_sha256"] == audit["record_sha256"]


def test_v5_modal_source_identity_stop_precedes_resource_or_system(
    tmp_path: Path, monkeypatch
) -> None:
    exact_spool = tmp_path / "frozen_spool"
    fresh_root = tmp_path / "fresh_run"
    exact_spool.mkdir()
    input_path = tmp_path / "input.dat"
    input_path.write_text("synthetic", encoding="utf-8")
    audit = authority.build_v5_operator_semantics_audit(
        source_sha="a" * 40,
        provenance={},
    )

    monkeypatch.setattr(
        level_a,
        "_v5_authority_identity_preflight",
        lambda **_kwargs: {
            "status": "identity_fail",
            "pass": False,
            "checks": {"modal_source_identity": False},
            "failures": ["modal_source_identity"],
            "observed": {},
            "expected": {},
            "operator_semantics_audit": audit,
        },
    )
    monkeypatch.setattr(
        level_a,
        "_v5_bare_f_resource_preflight",
        lambda *_args, **_kwargs: pytest.fail("resource preflight must not run"),
    )
    monkeypatch.setattr(
        level_a,
        "run_current_bare_f_authority",
        lambda *_args, **_kwargs: pytest.fail("system builder must not run"),
    )
    result = level_a.run_task040_level_a(
        object(),
        SimpleNamespace(bottom_interface_nm=10.0, top_interface_nm=110.0),
        comm=MPI.COMM_SELF,
        exact_spool_root=exact_spool,
        run_directory=fresh_root,
        source_sha="a" * 40,
        input_path=input_path,
        input_sha256="b" * 64,
        physical_model_sha256="c" * 64,
        v5_fresh_bare_f_authority=True,
    )
    assert result["classification"] == "FRESH_BARE_F_AUTHORITY_IDENTITY_FAIL"
    audit_binding = result["identity_preflight"]["operator_semantics_audit_file"]
    assert (
        audit_binding["sha256"]
        == hashlib.sha256(
            (fresh_root / "operator_semantics_audit.json").read_bytes()
        ).hexdigest()
    )


@pytest.fixture
def forbidden_research_constructor_guard(monkeypatch):
    calls: list[str] = []

    def guard(name: str):
        def fail(*_args, **_kwargs):
            calls.append(name)
            raise AssertionError(f"forbidden research constructor called: {name}")

        return fail

    import benchmarks.task039_v3_side_oracle as side_oracle
    import src.solvers.hybrid_local_dtn_action as dtn_action
    import src.solvers.hybrid_local_dtn_woodbury as woodbury

    monkeypatch.setattr(
        side_oracle,
        "_build_research_explicit_side_components",
        guard("C/D/H_builder"),
    )
    monkeypatch.setattr(
        dtn_action,
        "create_hybrid_local_dtn_action_components",
        guard("C/D/H_action_components"),
    )
    monkeypatch.setattr(
        woodbury,
        "ResearchExactSideLuAction",
        guard("ResearchExactSideLuAction"),
    )
    monkeypatch.setattr(
        woodbury,
        "create_research_exact_side_lu_action",
        guard("create_research_exact_side_lu_action"),
    )
    monkeypatch.setattr(
        woodbury,
        "HybridLocalDtnWoodburyOracle",
        guard("Woodbury_inverse"),
    )
    return calls


def test_external_minimal_rhs_matches_test_only_full_c_column(
    monkeypatch, forbidden_research_constructor_guard
) -> None:
    component_zero = np.asarray([1.0 + 2.0j, -3.0 + 0.5j, 2.0 - 1.0j])
    component_one = np.asarray([0.25 - 1.0j, 2.0 + 4.0j, -1.5 + 0.25j])
    traction = (0.5 - 0.25j, -1.5 + 0.75j)
    assembler_calls: list[tuple[int, int]] = []

    class FakeSurfaceComponentAssembler:
        def __init__(self, _V, _mesh_data, _tag, component, *, quadrature_degree):
            assembler_calls.append((int(component), int(quadrature_degree)))
            self.component = int(component)

        def assemble_unconstrained_vector(self, _mode):
            values = component_zero if self.component == 0 else component_one
            return PETSc.Vec().createWithArray(values.copy(), comm=PETSc.COMM_SELF)

    monkeypatch.setattr(
        authority,
        "_ReusableSurfaceComponentAssembler",
        FakeSurfaceComponentAssembler,
    )
    monkeypatch.setattr(
        authority,
        "_dtn_surface_quadrature_degree",
        lambda _cfg, _modes: 17,
    )
    traction_calls: list[object] = []

    def fake_traction_vector(mode, _cfg):
        traction_calls.append(mode)
        return np.asarray(traction, dtype=np.complex128)

    monkeypatch.setattr(authority, "_traction_vector", fake_traction_vector)
    monkeypatch.setattr(
        authority,
        "condense_unconstrained_vector_to_active_trace",
        lambda _condensed, vector, *, side: vector.copy(),
    )

    mode = SimpleNamespace(
        side="bottom",
        m=7,
        n=-3,
        polarization="s",
        alpha=0.2,
        gamma=-0.1,
        beta=0.4 + 0.02j,
        e_vector=np.asarray([99.0 + 0.0j, -77.0 + 0.0j, 42.0 + 0.0j]),
    )
    system = SimpleNamespace(
        cfg=SimpleNamespace(stage4_dtn_quadrature_degree=None),
        external_modes=(mode,),
        V=object(),
        local_mesh=SimpleNamespace(mesh_data=object(), external_facet_tag=11),
        condensed=object(),
        construction_inventory={
            "minimal_external_coupling_objects_constructed": 0,
            "minimal_external_surface_component_count": 0,
            "objects": {"C": 0, "D": 0, "H": 0},
        },
        dtn_objects_constructed={"C": 0, "D": 0, "H": 0},
    )
    expected_full_c_column = -(
        traction[0] * component_zero + traction[1] * component_one
    )
    minimal_vector, metadata = authority._external_minimal_c_vector(
        system, mode_index=0, sign=-1.0
    )
    repeat_vector, repeat_metadata = authority._external_minimal_c_vector(
        system, mode_index=0, sign=-1.0
    )
    try:
        np.testing.assert_allclose(
            minimal_vector.getArray(readonly=True), expected_full_c_column
        )
        np.testing.assert_allclose(
            repeat_vector.getArray(readonly=True), expected_full_c_column
        )
        assert assembler_calls == [(0, 17), (1, 17), (0, 17), (1, 17)]
        assert traction_calls == [mode, mode]
        assert metadata["traction_coefficients"] == [
            [traction[0].real, traction[0].imag],
            [traction[1].real, traction[1].imag],
        ]
        assert metadata["full_C_materialized"] is False
        assert repeat_metadata["full_C_materialized"] is False
        assert (
            system.construction_inventory[
                "minimal_external_coupling_construction_call_count"
            ]
            == 2
        )
        assert (
            system.construction_inventory["minimal_external_component_instances_total"]
            == 4
        )
        assert (
            system.construction_inventory["minimal_external_peak_live_components"] == 2
        )
        assert (
            system.construction_inventory["minimal_external_coupling_kind_count"] == 1
        )
        assert forbidden_research_constructor_guard == []
    finally:
        minimal_vector.destroy()
        repeat_vector.destroy()


def _synthetic_external_mode_authority() -> tuple[
    tuple[object, ...], dict[str, object]
]:
    modes = tuple(
        SimpleNamespace(
            side="bottom",
            m=index // 2,
            n=0,
            polarization="s" if index % 2 == 0 else "p",
            beta=0.5 + 0.001j * (index // 2),
            propagating=True,
            rayleigh_warning=False,
        )
        for index in range(296)
    )
    records = tuple(authority._external_mode_record(mode) for mode in modes)
    record_by_key = {
        json.dumps(
            {
                "side": item["side"],
                "m": item["m"],
                "n": item["n"],
                "polarization": item["polarization"],
            },
            sort_keys=True,
            separators=(",", ":"),
        ): item
        for item in records
    }
    keys = tuple(
        {
            "side": "bottom",
            "m": index,
            "n": 0,
            "polarization": polarization,
        }
        for index in range(148)
        for polarization in ("p", "s")
    )
    expected_records = tuple(
        record_by_key[json.dumps(key, sort_keys=True, separators=(",", ":"))]
        for key in keys
    )
    assert len(records) == len(expected_records) == 296
    return modes, {
        "count": 296,
        "canonical_keys": keys,
        "beta_metadata": expected_records,
        "canonical_key_list_sha256": authority.canonical_mode_keys_sha256(keys),
        "resolved_mode_metadata_sha256": authority.canonical_external_mode_metadata_sha256(
            expected_records
        ),
        "legacy_beta_metadata_sha256": "a" * 64,
        "legacy_beta_metadata_sha256_expected": "a" * 64,
        "resolved_config_sha256": "e" * 64,
        "current_resolved_config_sha256": "e" * 64,
        "index177_key": keys[177],
    }


def test_external_mode_authority_validator_rejects_key_order_beta_index_and_hash() -> (
    None
):
    modes, expected = _synthetic_external_mode_authority()
    ordered, _ordering_audit = authority._canonicalize_external_modes_by_authority(
        modes,
        expected,
        current_resolved_config_sha256=expected["current_resolved_config_sha256"],
    )
    audit = authority.validate_external_mode_authority(
        ordered,
        expected,
        current_resolved_config_sha256=expected["current_resolved_config_sha256"],
    )
    assert audit["pass"] is True
    assert (
        expected["resolved_mode_metadata_sha256"]
        != expected["legacy_beta_metadata_sha256"]
    )
    mutations: list[tuple[dict[str, object], str]] = []
    reordered = copy.deepcopy(expected)
    reordered["canonical_keys"] = tuple(reversed(reordered["canonical_keys"]))
    mutations.append((reordered, "ordered_keys"))
    beta_changed = copy.deepcopy(expected)
    beta_changed["beta_metadata"] = tuple(copy.deepcopy(expected["beta_metadata"]))
    beta_changed["beta_metadata"][177]["beta"][0] += 1.0
    mutations.append((beta_changed, "beta_metadata"))
    index_changed = copy.deepcopy(expected)
    index_changed["index177_key"] = {"side": "bottom", "m": -1}
    mutations.append((index_changed, "index177_key"))
    for field, check_name in (
        ("canonical_key_list_sha256", "canonical_key_list_sha256"),
        ("resolved_mode_metadata_sha256", "resolved_mode_metadata_sha256"),
        ("legacy_beta_metadata_sha256", "legacy_beta_metadata_sha256"),
        (
            "legacy_beta_metadata_sha256_expected",
            "legacy_beta_metadata_sha256",
        ),
        ("resolved_config_sha256", "resolved_config_sha256"),
    ):
        changed = copy.deepcopy(expected)
        changed[field] = "0" * 64
        mutations.append((changed, check_name))
    for mutation, check_name in mutations:
        with pytest.raises(authority.ExternalModeAuthorityIdentityError) as exc_info:
            authority.validate_external_mode_authority(
                ordered,
                mutation,
                current_resolved_config_sha256=expected[
                    "current_resolved_config_sha256"
                ],
            )
        assert exc_info.value.checks[check_name] is False


def test_external_mode_stream_is_reordered_to_frozen_authority_before_validation() -> (
    None
):
    modes, expected = _synthetic_external_mode_authority()
    raw_records = tuple(authority._external_mode_record(mode) for mode in modes)
    assert modes[177].polarization == "p"
    assert raw_records[177]["polarization"] == "p"
    ordered, audit = authority._canonicalize_external_modes_by_authority(
        modes,
        expected,
        current_resolved_config_sha256=expected["current_resolved_config_sha256"],
    )
    ordered_keys = tuple(
        {
            "side": str(mode.side),
            "m": int(mode.m),
            "n": int(mode.n),
            "polarization": str(mode.polarization),
        }
        for mode in ordered
    )
    assert ordered_keys == expected["canonical_keys"]
    assert ordered[177].polarization == "s"
    assert audit["permutation_only"] is True
    assert audit["raw_key_list_sha256"] != audit["canonical_key_list_sha256"]
    assert audit["raw_mode_metadata_sha256"] != audit["canonical_mode_metadata_sha256"]
    audit = authority.validate_external_mode_authority(
        ordered,
        expected,
        current_resolved_config_sha256=expected["current_resolved_config_sha256"],
    )
    assert audit["pass"] is True

    mutations = []
    duplicate_modes = list(modes)
    duplicate_modes[1] = duplicate_modes[0]
    mutations.append((tuple(duplicate_modes), "raw_key_unique"))
    mutations.append((modes[:1], "count"))
    beta_changed = list(modes)
    beta_changed[0] = SimpleNamespace(**{**vars(beta_changed[0]), "beta": 9.0 + 0.0j})
    mutations.append((tuple(beta_changed), "per_key_metadata"))
    classification_changed = list(modes)
    classification_changed[0] = SimpleNamespace(
        **{**vars(classification_changed[0]), "propagating": False}
    )
    mutations.append((tuple(classification_changed), "per_key_metadata"))
    rayleigh_changed = list(modes)
    rayleigh_changed[0] = SimpleNamespace(
        **{**vars(rayleigh_changed[0]), "rayleigh_warning": True}
    )
    mutations.append((tuple(rayleigh_changed), "per_key_metadata"))
    for mutated_modes, check_name in mutations:
        with pytest.raises(authority.FreshBareFAuthorityIdentityError) as exc_info:
            authority._canonicalize_external_modes_by_authority(
                mutated_modes,
                expected,
                current_resolved_config_sha256=expected[
                    "current_resolved_config_sha256"
                ],
            )
        assert (
            exc_info.value.details["external_mode_canonicalization"]["checks"][
                check_name
            ]
            is False
        )
    with pytest.raises(authority.FreshBareFAuthorityIdentityError) as exc_info:
        authority._canonicalize_external_modes_by_authority(modes, None)
    assert exc_info.value.failure_code == "EXTERNAL_MODE_AUTHORITY_UNAVAILABLE"
    with pytest.raises(authority.FreshBareFAuthorityIdentityError) as exc_info:
        authority._canonicalize_external_modes_by_authority(modes, expected)
    assert (
        exc_info.value.details["external_mode_canonicalization"]["checks"][
            "resolved_config_sha256"
        ]
        is False
    )


def test_v5_identity_preflight_binds_distinct_resolved_and_legacy_hashes(
    monkeypatch,
) -> None:
    def fake_git_run(arguments, **_kwargs):
        command = tuple(arguments[1:])
        outputs = {
            ("rev-parse", "HEAD"): "a" * 40,
            ("symbolic-ref", "--short", "HEAD"): level_a.TASK040_V4_FROZEN_BRANCH,
            (
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{upstream}",
            ): f"origin/{level_a.TASK040_V4_FROZEN_BRANCH}",
            ("rev-parse", "@{upstream}"): "a" * 40,
            ("rev-list", "--left-right", "--count", "HEAD...@{upstream}"): "0 0",
            ("status", "--porcelain", "--untracked-files=all"): "",
        }
        return SimpleNamespace(stdout=outputs[command])

    monkeypatch.setattr(level_a.subprocess, "run", fake_git_run)
    monkeypatch.setattr(
        level_a,
        "_v5_runtime_environment_preflight",
        lambda _comm, **_kwargs: {
            "pass": True,
            "checks": {
                "mpi_size": True,
                "petsc_scalar_complex128": True,
                "petsc_int_type_recorded": True,
                "qualified_activation": True,
                "repository_venv_executable": True,
                "threads_one": True,
                "process_tree_watchdog_enabled": True,
                "bottom_route_only": True,
            },
            "ranks": [{}],
        },
    )
    result = level_a._v5_authority_identity_preflight(
        comm=MPI.COMM_SELF,
        input_path=(
            Path("input/official/task039/")
            / "5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
        ),
        input_sha256=level_a.TASK040_V1_2_INPUT_SHA256,
        physical_model_sha256=level_a.TASK040_V1_2_PHYSICAL_MODEL_SHA256,
        source_sha="a" * 40,
        watchdog_enabled=True,
        bottom_route_only=True,
    )
    assert (
        result["observed"]["external_mode_resolved_mode_metadata_sha256"]
        == level_a.TASK040_V1_2_LOWER_RESOLVED_MODE_METADATA_SHA256
    )
    assert (
        result["observed"]["external_mode_legacy_beta_metadata_sha256"]
        == level_a.TASK040_V1_2_LOWER_LEGACY_BETA_METADATA_SHA256
    )
    assert result["checks"]["external_mode_resolved_mode_metadata_sha256"] is True
    assert result["checks"]["external_mode_legacy_beta_metadata_sha256"] is True


def test_external_mode_authority_validator_does_not_swallow_implementation_error(
    monkeypatch,
) -> None:
    modes, expected = _synthetic_external_mode_authority()
    monkeypatch.setattr(
        authority,
        "_external_mode_record",
        lambda _mode: (_ for _ in ()).throw(ValueError("shape/API failure")),
    )
    with pytest.raises(ValueError, match="shape/API failure"):
        authority.validate_external_mode_authority(
            modes,
            expected,
            current_resolved_config_sha256=expected["current_resolved_config_sha256"],
        )


def test_exact_modal_source_uses_one_paired_factor_and_independent_repeats(
    monkeypatch, forbidden_research_constructor_guard
) -> None:
    matrix = PETSc.Mat().createAIJ([4, 4], comm=PETSc.COMM_SELF)
    matrix.setUp()
    matrix.assemble()
    calls: list[dict[str, object]] = []

    def packet_provider(branch, index):
        beta = 0.2 + 0.01j if branch == "positive" else -0.2 - 0.01j
        return {
            "right_local": np.ones(2, dtype=np.complex128),
            "left_local": np.ones(2, dtype=np.complex128),
            "ownership_range": [0, 2],
            "global_size": 2,
            "beta": beta,
            "passive_branch_valid": True,
            "mode_key": {"branch": branch, "index": index},
            "manifest_path": "selected/manifest.json",
            "manifest_sha256": "a" * 64,
            "identity_sha256": "b" * 64,
        }

    def fake_trace(values, _spaces, _ownership_range, *, name):
        return SimpleNamespace(branch=name.split("_")[2])

    def fake_pair_builder(_cfg, traces, **kwargs):
        calls.append({"traces": set(traces), "kwargs": kwargs})
        callback = kwargs["stage_callback"]
        callback(
            "v5_one_cell_source_factor_ready",
            {
                "factor_count": 1,
                "factor_construction_count": 1,
                "peak_simultaneous_factor_count": 1,
            },
        )
        for apply_count, mat_solve_call_count, rhs_columns_solved in (
            (1, 1, 2),
            (2, 2, 4),
        ):
            callback(
                "v5_one_cell_source_factor_apply",
                {
                    "factor_count": 1,
                    "apply_count": apply_count,
                    "mat_solve_call_count": mat_solve_call_count,
                    "rhs_columns_solved": rhs_columns_solved,
                },
            )
        callback(
            "v5_one_cell_source_factor_destroyed",
            {
                "factor_count": 0,
                "factor_destroyed": True,
                "factor_matrix_alive": False,
                "mat_solve_call_count": 2,
                "rhs_columns_solved": 4,
            },
        )
        return (
            np.asarray([1, 3], dtype=PETSc.IntType),
            {
                "positive": {
                    "values": np.asarray([1.0, 2.0], dtype=np.complex128),
                    "repeat_values": np.asarray([1.0, 2.0], dtype=np.complex128),
                },
                "negative": {
                    "values": np.asarray([3.0, 4.0], dtype=np.complex128),
                    "repeat_values": np.asarray([3.0, 4.0], dtype=np.complex128),
                },
            },
            {
                "one_cell_factor_lifecycle": {
                    "factor_count_after": 0,
                    "factor_destroyed_before_return": True,
                    "factor_count_ready": 1,
                    "factor_construction_count": 1,
                    "apply_count": 2,
                    "mat_solve_call_count": 2,
                    "rhs_columns_solved": 4,
                    "peak_simultaneous_factor_count": 1,
                    "factor_matrix_alive_after_return": False,
                },
                "primal_endpoint_identity": {"pass": True},
            },
        )

    monkeypatch.setattr(authority, "_trace_from_streamed_local_values", fake_trace)
    monkeypatch.setattr(
        authority, "build_exact_one_cell_selected_traction_columns", fake_pair_builder
    )
    system = SimpleNamespace(
        cfg=object(),
        F=matrix,
        comm=MPI.COMM_SELF,
        source_work_directory=Path("/tmp/task040-v5-test"),
        selected_mode_provider=packet_provider,
        _selected_mode_context=authority._SelectedModeSourceContext(
            packet_provider=packet_provider, spaces=object()
        ),
        _selected_exact_source_cache=None,
        construction_inventory={
            "objects": {"C": 0, "D": 0, "H": 0},
            "one_cell_source_factor_events": [],
            "one_cell_source_factor_active": 0,
            "one_cell_source_factor_peak": 0,
            "one_cell_source_factor_ready": 0,
            "one_cell_source_factor_destroyed": False,
            "one_cell_source_factor_factor_count_after": None,
            "one_cell_source_factor_mat_solve_call_count": 0,
            "one_cell_source_factor_rhs_columns_solved": 0,
            "source_build_counts": {
                name: 0 for name in authority.V5_BARE_F_SOURCE_LABELS
            },
        },
        dtn_objects_constructed={"C": 0, "D": 0, "H": 0},
    )
    marker_events: list[tuple[str, dict[str, object]]] = []
    system.source_factor_marker_callback = lambda stage, detail: marker_events.append(
        (stage, dict(detail))
    )
    try:
        for label, branch, index in (
            ("modal_traction_positive", "positive", 281),
            ("modal_traction_negative", "negative", 283),
        ):
            system.construction_inventory["source_build_counts"][label] += 1
            vector, metadata = authority._selected_mode_internal_traction_vector(
                system, branch=branch, mode_index=index, label=label
            )
            np.testing.assert_allclose(
                vector.getArray(readonly=True),
                [0.0, 1.0, 0.0, 2.0] if branch == "positive" else [0.0, 3.0, 0.0, 4.0],
            )
            assert metadata["selected_mode_packet_global_size"] == 2
            assert metadata["current_active_rhs_global_size"] == 4
            vector.destroy()
            assert metadata["rhs_generation"] == "first"
            system.construction_inventory["source_build_counts"][label] += 1
            vector, metadata = authority._selected_mode_internal_traction_vector(
                system, branch=branch, mode_index=index, label=label
            )
            np.testing.assert_allclose(
                vector.getArray(readonly=True),
                [0.0, 1.0, 0.0, 2.0] if branch == "positive" else [0.0, 3.0, 0.0, 4.0],
            )
            vector.destroy()
            assert metadata["rhs_generation"] == "independent_repeat"
        assert len(calls) == 1
        assert calls[0]["traces"] == {"positive", "negative"}
        assert calls[0]["kwargs"]["positive_beta"] == 0.2 + 0.01j
        assert calls[0]["kwargs"]["negative_beta"] == -0.2 - 0.01j
        assert (
            system.construction_inventory["one_cell_source_factor_construction_count"]
            == 1
        )
        assert system.construction_inventory["one_cell_source_factor_apply_count"] == 2
        assert (
            system.construction_inventory["one_cell_source_factor_mat_solve_call_count"]
            == 2
        )
        assert (
            system.construction_inventory["one_cell_source_factor_rhs_columns_solved"]
            == 4
        )
        assert system.construction_inventory["one_cell_source_factor_ready"] == 1
        assert system.construction_inventory["one_cell_source_factor_destroyed"] is True
        assert (
            system.construction_inventory["one_cell_source_factor_factor_count_after"]
            == 0
        )
        assert system.construction_inventory["one_cell_source_factor_active"] == 0
        assert system.construction_inventory["one_cell_source_factor_peak"] == 1
        assert [stage for stage, _detail in marker_events] == [
            "v5_one_cell_source_factor_ready",
            "v5_one_cell_source_factor_apply",
            "v5_one_cell_source_factor_apply",
            "v5_one_cell_source_factor_destroyed",
            "v5_one_cell_source_cleanup_complete",
        ]
        assert all(
            detail["factor_scope"] == "one_cell_source"
            for _stage, detail in marker_events
        )
        assert forbidden_research_constructor_guard == []
    finally:
        matrix.destroy()


def test_bare_f_uses_narrow_trace_reduction_adapter(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    expected = object()

    def fake_project(condensed, vector, **kwargs):
        calls.append(kwargs)
        assert condensed == "condensed"
        return expected

    monkeypatch.setattr(authority, "project_mpc_vector_to_active_trace", fake_project)
    adapter = authority._BareFStaticCondensationAdapter("condensed")
    assert (
        adapter.reduce_tangential_surface_mpc_vector("vector", audit={"ok": True})
        is expected
    )
    assert calls == [
        {
            "eliminated_tolerance": 1.0e-12,
            "eliminated_relative_tolerance": 1024.0 * np.finfo(float).eps,
            "audit": {"ok": True},
        }
    ]


def test_current_active_target_rows_reject_bad_bounds_and_owner_coverage() -> None:
    with pytest.raises(ValueError, match="outside the F bounds"):
        authority._validate_current_active_target_rows(
            np.asarray([0, 4]),
            np.ones(2, dtype=np.complex128),
            current_global_size=4,
            current_ownership_range=(0, 4),
            all_ownership_ranges=((0, 4),),
            all_target_row_shards=((0, 4),),
        )
    with pytest.raises(ValueError, match="outside its owner range"):
        authority._validate_current_active_target_rows(
            np.asarray([2]),
            np.ones(1, dtype=np.complex128),
            current_global_size=4,
            current_ownership_range=(0, 2),
            all_ownership_ranges=((0, 2), (2, 4)),
            all_target_row_shards=((2,), (3,)),
        )
    with pytest.raises(ValueError, match="contain duplicates"):
        authority._validate_current_active_target_rows(
            np.asarray([1, 1]),
            np.ones(2, dtype=np.complex128),
            current_global_size=4,
            current_ownership_range=(0, 4),
            all_ownership_ranges=((0, 4),),
            all_target_row_shards=((1, 1),),
        )


def test_current_active_target_rows_accept_different_owner_local_shards() -> None:
    owned, audit = authority._validate_current_active_target_rows(
        np.asarray([1]),
        np.ones(1, dtype=np.complex128),
        current_global_size=4,
        current_ownership_range=(0, 2),
        all_ownership_ranges=((0, 2), (2, 4)),
        all_target_row_shards=((1,), (3,)),
    )
    assert owned.tolist() == [True]
    assert audit["owner_coverage"] == {
        "pass": True,
        "global_target_row_count": 2,
        "global_unique_target_row_count": 2,
        "mpi_size": 2,
    }


def test_current_active_target_rows_real_mpi_vec_owner_scatter() -> None:
    comm = MPI.COMM_WORLD
    global_size = max(4 * int(comm.size), 2)
    vector = PETSc.Vec().createMPI((PETSc.DECIDE, global_size), comm=comm)
    try:
        first, last = map(int, vector.getOwnershipRange())
        ownership_range = (first, last)
        target_rows = np.arange(first, last, dtype=np.int64)
        values = np.asarray(
            [complex(comm.rank + 1, int(row)) for row in target_rows],
            dtype=np.complex128,
        )
        all_ownership_ranges = tuple(comm.allgather(ownership_range))
        all_target_row_shards = tuple(
            comm.allgather(tuple(int(row) for row in target_rows))
        )
        owned, audit = authority._validate_current_active_target_rows(
            target_rows,
            values,
            current_global_size=global_size,
            current_ownership_range=ownership_range,
            all_ownership_ranges=all_ownership_ranges,
            all_target_row_shards=all_target_row_shards,
        )
        gathered_rows = [row for shard in all_target_row_shards for row in shard]
        assert owned.tolist() == [True] * len(target_rows)
        assert len(gathered_rows) == global_size
        assert len(gathered_rows) == len(set(gathered_rows))
        assert set(gathered_rows) == set(range(global_size))
        assert audit["owner_coverage"]["pass"] is True
        assert comm.allreduce(bool(np.all(owned)), op=MPI.LAND)
    finally:
        vector.destroy()


def test_canonical_identity_failure_payload_is_seen_collectively() -> None:
    class FakeComm:
        def allgather(self, payload):
            assert payload is None
            return [
                None,
                {
                    "failure_code": "CANONICAL_ACTIVE_KEY_SET_IDENTITY_FAIL",
                    "message": "duplicate key",
                    "stage": "canonical_layout_validation",
                    "details": {},
                },
            ]

    with pytest.raises(
        authority.FreshBareFAuthorityIdentityError,
        match="duplicate key",
    ) as exc_info:
        authority._collective_raise_fresh_bare_f_identity(FakeComm(), None)
    assert exc_info.value.failure_code == "CANONICAL_ACTIVE_KEY_SET_IDENTITY_FAIL"
    assert exc_info.value.stage == "canonical_layout_validation"


def test_collective_identity_stop_cleans_local_temporary_after_decision() -> None:
    class FakeComm:
        def allgather(self, payload):
            assert payload is None
            return [
                None,
                {
                    "failure_code": "CURRENT_ACTIVE_TARGET_ROW_IDENTITY_FAIL",
                    "message": "owner mismatch",
                    "stage": "source_mapping",
                    "details": {},
                },
            ]

    cleaned: list[str] = []
    with pytest.raises(authority.FreshBareFAuthorityIdentityError):
        authority._collective_identity_stop_with_cleanup(
            FakeComm(), None, lambda: cleaned.append("destroyed")
        )
    assert cleaned == ["destroyed"]


def test_one_cell_source_identity_gate_decides_collectively() -> None:
    class FakeComm:
        def allgather(self, payload):
            assert payload is None
            return [None, {"message": "dual identity mismatch", "stage": "dual"}]

    with pytest.raises(one_cell_builder.ExactOneCellSourceIdentityError) as exc_info:
        one_cell_builder._collective_source_identity_gate(FakeComm(), None)
    assert str(exc_info.value) == "dual identity mismatch"
    assert exc_info.value.stage == "dual"


def test_identity_gate_is_collective_and_prevents_factor_constructor(monkeypatch):
    constructor_calls: list[object] = []

    monkeypatch.setattr(
        authority,
        "ResearchExactFactorInverse",
        lambda *_args, **_kwargs: constructor_calls.append(object()),
    )
    local_error = authority.FreshBareFAuthorityIdentityError(
        "RHS_REPEAT_IDENTITY_FAIL",
        "synthetic local identity failure",
        stage="rhs_generation",
        details={"rank": 0},
    )
    with pytest.raises(authority.FreshBareFAuthorityIdentityError):
        authority._collective_raise_fresh_bare_f_identity(
            MPI.COMM_SELF,
            local_error,
        )
    with pytest.raises(authority.FreshBareFAuthorityIdentityError):
        authority._construct_bare_f_factor_after_identity_gate(False, object())
    assert constructor_calls == []


def test_factor_constructor_implementation_error_is_not_identity_swallowed(
    monkeypatch,
):
    def fail_constructor(*_args, **_kwargs):
        raise ValueError("factor API failure")

    monkeypatch.setattr(authority, "ResearchExactFactorInverse", fail_constructor)
    with pytest.raises(ValueError, match="factor API failure"):
        authority._construct_bare_f_factor_after_identity_gate(True, object())


def test_bare_f_factor_markers_bind_explicit_current_operator(monkeypatch) -> None:
    class FakeFactor:
        def __init__(self, *_args, **_kwargs):
            pass

        diagnostics = {
            "direct_factor_count": 1,
            "factor_matrix_alive": True,
        }

    monkeypatch.setattr(authority, "ResearchExactFactorInverse", FakeFactor)
    events: list[tuple[str, dict[str, object]]] = []
    factor = authority._construct_bare_f_factor_after_identity_gate(
        True,
        object(),
        marker_callback=lambda stage, detail: events.append((stage, detail)),
        operator_hash="a" * 64,
    )
    assert factor.diagnostics["direct_factor_count"] == 1
    assert [stage for stage, _detail in events] == [
        "v5_bare_f_factor_setup_begin",
        "v5_bare_f_factor_ready",
    ]
    assert all(
        detail["factored_operator"] == "explicit_current_bare_F"
        and detail["operator_hash"] == "a" * 64
        for _stage, detail in events
    )


def test_late_identity_stop_bookkeeping_preserves_generated_work() -> None:
    rhs_vectors = {
        authority.V5_BARE_F_SOURCE_LABELS[0]: object(),
        "__temporary_exact__modal_traction_positive": object(),
    }
    exact_records = {authority.V5_BARE_F_SOURCE_LABELS[0]: {"array_sha256": "a" * 64}}
    bookkeeping = authority._fresh_bare_f_identity_stop_bookkeeping(
        rhs_vectors=rhs_vectors,
        exact_records=exact_records,
        inventory={
            "minimal_external_coupling_objects_constructed": 1,
            "minimal_external_surface_component_count": 2,
        },
        factor_ready={"direct_factor_count": 1},
        factor_after={"direct_factor_count": 0, "solve_count": 2},
        stage="packet_binding",
        system_created=True,
    )
    assert bookkeeping["rhs_vectors_loaded"] == 1
    assert bookkeeping["exact_output_vectors_loaded"] == 1
    assert bookkeeping["factor_stage"] == "after_factor"
    assert (
        bookkeeping["external_dtn_status"]
        == "minimal_rhs_constructed_before_identity_stop"
    )
    assert bookkeeping["gate_status"] == "identity_failed_after_factor"
    assert bookkeeping["system_created"] is True


def test_v5_runner_forwards_fresh_output_root_and_never_spool_root(
    tmp_path: Path, monkeypatch
) -> None:
    exact_spool = tmp_path / "frozen_spool"
    fresh_root = tmp_path / "fresh_run"
    exact_spool.mkdir()
    input_path = tmp_path / "official_input.dat"
    input_path.write_text("synthetic input", encoding="utf-8")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        level_a,
        "_v5_authority_identity_preflight",
        lambda **_kwargs: {
            "status": "pass",
            "pass": True,
            "checks": {},
            "failures": [],
            "observed": {},
            "expected": {},
            "external_mode_authority": {},
        },
    )
    monkeypatch.setattr(
        level_a,
        "_v5_bare_f_resource_preflight",
        lambda comm, run_directory: {"pass": True, "ranks": [{}]},
    )
    monkeypatch.setattr(
        level_a,
        "_v5_selected_mode_provider",
        lambda comm: object(),
    )

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return {"schema": level_a.TASK040_V5_FRESH_BARE_F_AUTHORITY_SCHEMA}

    monkeypatch.setattr(level_a, "run_current_bare_f_authority", fake_run)
    result = level_a.run_task040_level_a(
        object(),
        SimpleNamespace(bottom_interface_nm=10.0, top_interface_nm=110.0),
        comm=MPI.COMM_SELF,
        exact_spool_root=exact_spool,
        run_directory=fresh_root,
        source_sha="a" * 40,
        input_path=input_path,
        input_sha256="b" * 64,
        physical_model_sha256="c" * 64,
        v5_fresh_bare_f_authority=True,
    )
    assert result["schema"] == level_a.TASK040_V5_FRESH_BARE_F_AUTHORITY_SCHEMA
    assert Path(captured["run_directory"]).resolve() == fresh_root.resolve()
    assert not (exact_spool / "bare_f_authority").exists()

    with pytest.raises(ValueError, match="must not be the frozen exact spool root"):
        level_a.run_task040_level_a(
            object(),
            SimpleNamespace(bottom_interface_nm=10.0, top_interface_nm=110.0),
            comm=MPI.COMM_SELF,
            exact_spool_root=exact_spool,
            run_directory=exact_spool,
            source_sha="a" * 40,
            input_path=input_path,
            input_sha256="b" * 64,
            physical_model_sha256="c" * 64,
            v5_fresh_bare_f_authority=True,
        )


def test_v5_watchdog_plan_records_memory_gate_and_process_group_contract() -> None:
    plan = watchdog.build_task040_level_a_watchdog_plan(
        input_path="input.dat",
        exact_spool_root="frozen_spool",
        run_directory="fresh_run",
        source_sha="a" * 40,
        v5_fresh_bare_f_authority=True,
    )
    assert plan["watchdog"]["preferred_memory_bytes"] == 55 * 2**30
    assert plan["watchdog"]["warning_memory_bytes"] == 58 * 2**30
    assert plan["watchdog"]["hard_stop_bytes"] == 64 * 2**30
    assert plan["watchdog"]["terminate_entire_process_group"] is True
    assert plan["watchdog"]["process_tree_watchdog_enabled"] is True
    assert plan["watchdog"]["bottom_route_only"] is True
    assert plan["watchdog"]["swap_limit_bytes"] == 0
    assert plan["worker_argv"][0:2] == ["mpiexec", "-n"]
    assert "--v5-fresh-bare-f-authority" in plan["worker_argv"]
    assert "--watchdog-enabled" in plan["worker_argv"]
    assert "--bottom-route-only" in plan["worker_argv"]


def test_v5_runtime_preflight_records_actual_environment(monkeypatch) -> None:
    class FakeComm:
        size = 8

        @staticmethod
        def allgather(payload):
            return [payload] * 8

        @staticmethod
        def allreduce(value, op):
            assert op == MPI.LAND
            return value

    monkeypatch.setenv("_MYFENICS_WSL_QUALIFIED_ACTIVATION", "1")
    for name in level_a.TASK040_V5_REQUIRED_THREAD_ENV:
        monkeypatch.setenv(name, "1")
    result = level_a._v5_runtime_environment_preflight(
        FakeComm(),
        watchdog_enabled=True,
        bottom_route_only=True,
    )
    assert result["pass"] is True
    assert result["checks"] == {
        "mpi_size": True,
        "petsc_scalar_complex128": True,
        "petsc_int_type_recorded": True,
        "qualified_activation": True,
        "repository_venv_executable": True,
        "threads_one": True,
        "process_tree_watchdog_enabled": True,
        "bottom_route_only": True,
    }
    observed = result["ranks"][0]
    assert observed["comm_size"] == 8
    assert observed["petsc_scalar_type"] == "complex128"
    assert observed["threads_per_rank"] == 1
    assert observed["process_tree_watchdog_enabled"] is True
    assert observed["bottom_route_only"] is True


def test_v5_runtime_preflight_failure_is_explicit_and_stops_before_system(
    tmp_path: Path, monkeypatch
) -> None:
    exact_spool = tmp_path / "frozen_spool"
    fresh_root = tmp_path / "fresh_run"
    exact_spool.mkdir()
    input_path = tmp_path / "official_input.dat"
    input_path.write_text("synthetic input", encoding="utf-8")
    identity = {
        "status": "identity_fail",
        "pass": False,
        "checks": {"runtime_mpi_size": False},
        "failures": ["runtime_mpi_size"],
        "observed": {},
        "expected": {},
        "external_mode_authority": {},
        "runtime_preflight": {
            "pass": False,
            "checks": {"mpi_size": False},
            "ranks": [{"comm_size": 1}],
        },
    }
    monkeypatch.setattr(
        level_a,
        "_v5_authority_identity_preflight",
        lambda **_kwargs: identity,
    )
    monkeypatch.setattr(
        level_a,
        "_v5_bare_f_resource_preflight",
        lambda *_args, **_kwargs: pytest.fail("resource preflight must not run"),
    )
    monkeypatch.setattr(
        level_a,
        "run_current_bare_f_authority",
        lambda *_args, **_kwargs: pytest.fail("system/factor must not run"),
    )
    result = level_a.run_task040_level_a(
        object(),
        SimpleNamespace(bottom_interface_nm=10.0, top_interface_nm=110.0),
        comm=MPI.COMM_SELF,
        exact_spool_root=exact_spool,
        run_directory=fresh_root,
        source_sha="a" * 40,
        input_path=input_path,
        input_sha256="b" * 64,
        physical_model_sha256="c" * 64,
        v5_fresh_bare_f_authority=True,
    )
    assert result["status"] == "not_run_by_resource_preflight"
    assert result["classification"] == "FRESH_BARE_F_AUTHORITY_RESOURCE_BLOCKED"
    assert result["system_created"] is False
    assert result["runtime_preflight"]["checks"]["mpi_size"] is False


def test_canonical_packets_accept_unhashable_physical_keys(monkeypatch) -> None:
    packets = (({"m": 1}, 1.0 + 0.0j), ({"m": 2}, 2.0 + 0.0j))
    monkeypatch.setattr(
        authority,
        "extract_canonical_active_trace_packets",
        lambda *_args: (packets, {"synthetic": True}),
    )
    system = SimpleNamespace(
        comm=MPI.COMM_SELF,
        condensed=object(),
        V=object(),
        floquet_data=object(),
    )
    extracted, audit = authority._canonical_packets_collective_safe(system, object())
    assert extracted == packets
    assert audit == {"synthetic": True}


def test_canonical_unknown_implementation_error_exits_collectively(monkeypatch) -> None:
    def extract_with_rank_zero_failure(*_args):
        if MPI.COMM_WORLD.rank == 0:
            raise ValueError("unexpected API shape")
        return (({"m": 1}, 1.0 + 0.0j),), {"synthetic": True}

    monkeypatch.setattr(
        authority,
        "extract_canonical_active_trace_packets",
        extract_with_rank_zero_failure,
    )
    system = SimpleNamespace(
        comm=MPI.COMM_WORLD,
        condensed=object(),
        V=object(),
        floquet_data=object(),
    )
    with pytest.raises(ValueError, match="unexpected API shape") as exc_info:
        authority._canonical_packets_collective_safe(system, object())
    assert "collective implementation failure" in str(exc_info.value)
    assert getattr(exc_info.value, "source_rank") == 0
    assert getattr(exc_info.value, "stage") == "canonical_packet_extraction"


def test_canonical_roundtrip_unknown_value_error_is_implementation_failure(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        authority,
        "canonical_to_current_roundtrip_relative",
        lambda *_args: (_ for _ in ()).throw(ValueError("unexpected API shape")),
    )
    system = SimpleNamespace(comm=MPI.COMM_SELF)
    with pytest.raises(ValueError, match="unexpected API shape"):
        authority._canonical_roundtrip_or_identity_stop(
            system,
            ("key",),
            np.asarray([1.0 + 0.0j]),
            object(),
            label="fixed_random_repeat_0",
            stage="test",
        )


def test_gamma_planes_follow_frozen_three_group_indices() -> None:
    source = inspect.getsource(authority.run_current_bare_f_authority)
    assert "system.local_mesh.z_values[2]" in source
    assert "system.local_mesh.z_values[4]" in source
    assert "external_z_nm" not in source[source.index("gamma_layouts") :]


def test_source_core_has_no_benchmark_or_task_provider_import() -> None:
    source = inspect.getsource(authority)
    assert "from benchmarks" not in source
    assert "import benchmarks" not in source
    assert "selected_mode_provider" in source


def test_forbidden_research_side_actions_are_not_called_by_fresh_route() -> None:
    source = inspect.getsource(authority.run_current_bare_f_authority)
    assert "ResearchExactSideLuAction" not in source
    assert "create_research_exact_side_lu_action" not in source
    assert "Woodbury" not in source
    assert "ResearchExactFactorInverse" in source


def test_owner_row_packet_is_separate_from_canonical_packet(tmp_path: Path) -> None:
    identity = {
        "finite": True,
        "raw_global_row_remap": False,
        "canonical_to_current_roundtrip_relative": 0.0,
    }
    record = authority._write_vector_packet(
        root=tmp_path,
        rank=0,
        label="fixed_random_repeat_0",
        role="rhs",
        tokens=("k0", "k1"),
        values=np.asarray([1.0 + 0.0j, 2.0 + 0.0j]),
        owner_values=np.asarray([2.0 + 0.0j, 1.0 + 0.0j]),
        identity=identity,
        source_metadata={
            "source": "test",
            "source_definition_sha256": "d" * 64,
            "bare_f_operator_hash": "f" * 64,
        },
        key_set_sha256="d" * 64,
        canonical_layout_sha256="e" * 64,
    )
    assert Path(tmp_path / record["array_path"]).is_file()
    assert Path(tmp_path / record["owner_row_array_path"]).is_file()
    assert record["owner_row_array_sha256"] != record["array_sha256"]
    for source_definition_sha256, bare_f_operator_hash in (
        ("", "f" * 64),
        ("d" * 64, "not-a-sha256"),
    ):
        with pytest.raises(ValueError):
            authority._write_vector_packet(
                root=tmp_path,
                rank=0,
                label="fixed_random_repeat_0",
                role="rhs",
                tokens=("k0", "k1"),
                values=np.asarray([1.0 + 0.0j, 2.0 + 0.0j]),
                owner_values=np.asarray([2.0 + 0.0j, 1.0 + 0.0j]),
                identity=identity,
                source_metadata={
                    "source": "test",
                    "source_definition_sha256": source_definition_sha256,
                    "bare_f_operator_hash": bare_f_operator_hash,
                },
                key_set_sha256="d" * 64,
                canonical_layout_sha256="e" * 64,
            )


def _synthetic_owner_packet_fixture() -> dict[str, object]:
    labels = authority.V5_BARE_F_SOURCE_LABELS
    owner_shards = []
    rhs_records = {}
    exact_records = {}
    gamma_records = {}
    gamma_layout_records = {}
    source_definition_hashes = {label: [] for label in labels}
    for rank in range(8):
        rank_key = str(rank)
        layout_sha = f"{rank + 1:064x}"
        owner_shards.append(
            {
                "rank": rank,
                "sha256": f"{rank + 9:064x}",
                "canonical_layout": {"sha256": layout_sha},
            }
        )
        rhs_records[rank_key] = {}
        exact_records[rank_key] = {}
        gamma_records[rank_key] = {}
        gamma_layout_records[rank_key] = {
            "Gamma_L": {"sha256": f"{rank + 20:064x}"},
            "Gamma_U": {"sha256": f"{rank + 30:064x}"},
        }
        for index, label in enumerate(labels):
            source_hash = hashlib.sha256(label.encode()).hexdigest()
            source_definition_hashes[label].append(source_hash)
            provenance = {
                "input_sha256": "1" * 64,
                "physical_model_sha256": "2" * 64,
                "selected_manifest_sha256": "3" * 64,
                "selected_identity_sha256": "4" * 64,
                "resolved_config_sha256": "5" * 64,
                "source_sha": "c" * 40,
            }
            shared = {
                "source_definition_sha256": source_hash,
                "bare_f_operator_hash": "f" * 64,
                "canonical_key_set_sha256": "6" * 64,
                "canonical_layout_sha256": layout_sha,
                "source_provenance": provenance,
            }
            rhs_array_sha = f"{100 + rank * 10 + index:064x}"
            rhs_owner_sha = f"{200 + rank * 10 + index:064x}"
            rhs_identity = {
                "array_sha256": rhs_array_sha,
                "owner_row_array_sha256": rhs_owner_sha,
                "global_sha256": "0" * 64,
                "canonical_key_set_sha256": "6" * 64,
                "global_size": 16,
                "local_size": 2,
                "ownership_range": [2 * rank, 2 * rank + 2],
                "canonical_to_current_roundtrip_relative": 0.0,
                "finite": True,
            }
            rhs_records[rank_key][label] = {
                **shared,
                "role": "rhs",
                "label": label,
                "array_sha256": rhs_array_sha,
                "owner_row_array_sha256": rhs_owner_sha,
                "global_sha256": "0" * 64,
                "canonical_key_set_sha256": "6" * 64,
                "global_size": 16,
                "local_size": 2,
                "ownership_range": [2 * rank, 2 * rank + 2],
                "canonical_to_current_roundtrip_relative": 0.0,
                "finite": True,
                "source_definition": {
                    "source_definition_sha256": source_hash,
                    "rhs_repeat": {"pass": True},
                },
                "vector_identity": rhs_identity,
            }
            exact_array_sha = f"{400 + rank * 10 + index:064x}"
            exact_owner_sha = f"{500 + rank * 10 + index:064x}"
            exact_identity = {
                "array_sha256": exact_array_sha,
                "owner_row_array_sha256": exact_owner_sha,
                "global_sha256": "0" * 64,
                "canonical_key_set_sha256": "6" * 64,
                "global_size": 16,
                "local_size": 2,
                "ownership_range": [2 * rank, 2 * rank + 2],
                "canonical_to_current_roundtrip_relative": 0.0,
                "finite": True,
            }
            exact_records[rank_key][label] = {
                **shared,
                "role": "exact_output",
                "label": label,
                "array_sha256": exact_array_sha,
                "owner_row_array_sha256": exact_owner_sha,
                "global_sha256": "0" * 64,
                "global_size": 16,
                "local_size": 2,
                "ownership_range": [2 * rank, 2 * rank + 2],
                "canonical_to_current_roundtrip_relative": 0.0,
                "finite": True,
                "source_definition": {
                    "source_definition_sha256": source_hash,
                    "rhs_repeat": {"pass": True},
                },
                "vector_identity": exact_identity,
            }
            gamma_records[rank_key][label] = {
                gamma_name: {
                    **shared,
                    "role": "exact_trace",
                    "label": label,
                    "gamma": gamma_name,
                    "layout_sha256": gamma_layout_records[rank_key][gamma_name][
                        "sha256"
                    ],
                    "array_sha256": f"{700 + rank * 10 + index * 2 + offset:064x}",
                    "global_sha256": "0" * 64,
                    "rank_local_shard_binding_sha256": "0" * 64,
                }
                for offset, gamma_name in enumerate(("Gamma_L", "Gamma_U"))
            }
    for records in (rhs_records, exact_records):
        for label in labels:
            local_hashes = [
                records[str(rank)][label]["array_sha256"] for rank in range(8)
            ]
            global_hash = hashlib.sha256("\n".join(local_hashes).encode()).hexdigest()
            for rank in range(8):
                record = records[str(rank)][label]
                record["global_sha256"] = global_hash
                record["vector_identity"]["global_sha256"] = global_hash
                record["rank_local_shard_binding_sha256"] = (
                    authority._rank_local_shard_binding_sha256(
                        rank=rank,
                        label=label,
                        role=record["role"],
                        source_definition_sha256=record["source_definition_sha256"],
                        key_set_sha256=record["canonical_key_set_sha256"],
                        canonical_layout_sha256=record["canonical_layout_sha256"],
                        identity=record["vector_identity"],
                        source_provenance=record["source_provenance"],
                        bare_f_operator_hash=record["bare_f_operator_hash"],
                        rhs_repeat=record["source_definition"]["rhs_repeat"],
                    )
                )
    for label in labels:
        for gamma_name in ("Gamma_L", "Gamma_U"):
            gamma_hashes = [
                gamma_records[str(rank)][label][gamma_name]["array_sha256"]
                for rank in range(8)
            ]
            global_hash = hashlib.sha256("\n".join(gamma_hashes).encode()).hexdigest()
            for rank in range(8):
                record = gamma_records[str(rank)][label][gamma_name]
                record["global_sha256"] = global_hash
                record["rank_local_shard_binding_sha256"] = hashlib.sha256(
                    json.dumps(
                        {
                            "rank": rank,
                            "label": label,
                            "role": "exact_trace",
                            "gamma": gamma_name,
                            "source_definition_sha256": record[
                                "source_definition_sha256"
                            ],
                            "canonical_key_set_sha256": record[
                                "canonical_key_set_sha256"
                            ],
                            "layout_sha256": record["layout_sha256"],
                            "array_sha256": record["array_sha256"],
                            "bare_f_operator_hash": record["bare_f_operator_hash"],
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
    return {
        "owner_shards": owner_shards,
        "all_rhs_records": rhs_records,
        "all_exact_records": exact_records,
        "all_gamma_records": gamma_records,
        "all_gamma_layout_records": gamma_layout_records,
        "source_definition_hashes": source_definition_hashes,
    }


def test_owner_packet_binding_helper_accepts_complete_eight_rank_fixture() -> None:
    fixture = _synthetic_owner_packet_fixture()
    assert (
        authority._check_owner_packet_bindings(
            **fixture,
            bare_f_operator_hash="f" * 64,
        )
        is True
    )

    def refresh_binding(record: dict[str, object], rank: int) -> None:
        source_definition = record["source_definition"]
        record["rank_local_shard_binding_sha256"] = (
            authority._rank_local_shard_binding_sha256(
                rank=rank,
                label=str(record["label"]),
                role=str(record["role"]),
                source_definition_sha256=str(record["source_definition_sha256"]),
                key_set_sha256=str(record["canonical_key_set_sha256"]),
                canonical_layout_sha256=str(record["canonical_layout_sha256"]),
                identity=record["vector_identity"],
                source_provenance=record["source_provenance"],
                bare_f_operator_hash=str(record["bare_f_operator_hash"]),
                rhs_repeat=source_definition["rhs_repeat"],
            )
        )

    mutations = []
    changed_source = copy.deepcopy(fixture)
    changed_source["all_rhs_records"]["0"]["modal_traction_positive"][
        "source_definition_sha256"
    ] = "0" * 64
    mutations.append(changed_source)
    changed_operator = copy.deepcopy(fixture)
    changed_operator["all_exact_records"]["0"]["modal_traction_positive"][
        "bare_f_operator_hash"
    ] = "0" * 64
    mutations.append(changed_operator)
    missing_rank = copy.deepcopy(fixture)
    del missing_rank["all_rhs_records"]["7"]
    mutations.append(missing_rank)
    missing_label = copy.deepcopy(fixture)
    del missing_label["all_exact_records"]["0"]["modal_traction_positive"]
    mutations.append(missing_label)
    changed_gamma_layout = copy.deepcopy(fixture)
    changed_gamma_layout["all_gamma_layout_records"]["0"]["Gamma_L"]["sha256"] = (
        "0" * 64
    )
    mutations.append(changed_gamma_layout)
    changed_binding = copy.deepcopy(fixture)
    changed_binding["all_rhs_records"]["0"]["modal_traction_positive"][
        "rank_local_shard_binding_sha256"
    ] = "9" * 64
    mutations.append(changed_binding)
    changed_global = copy.deepcopy(fixture)
    changed_global["all_exact_records"]["0"]["modal_traction_positive"][
        "global_sha256"
    ] = "8" * 64
    changed_global["all_exact_records"]["0"]["modal_traction_positive"][
        "vector_identity"
    ]["global_sha256"] = "8" * 64
    refresh_binding(
        changed_global["all_exact_records"]["0"]["modal_traction_positive"],
        0,
    )
    mutations.append(changed_global)
    changed_identity = copy.deepcopy(fixture)
    changed_identity["all_rhs_records"]["0"]["modal_traction_positive"][
        "array_sha256"
    ] = "7" * 64
    mutations.append(changed_identity)
    changed_key_identity = copy.deepcopy(fixture)
    changed_key_identity["all_rhs_records"]["0"]["modal_traction_positive"][
        "vector_identity"
    ]["canonical_key_set_sha256"] = "a" * 64
    mutations.append(changed_key_identity)
    changed_range = copy.deepcopy(fixture)
    changed_range["all_rhs_records"]["1"]["modal_traction_positive"][
        "ownership_range"
    ] = [3, 5]
    changed_range["all_rhs_records"]["1"]["modal_traction_positive"]["vector_identity"][
        "ownership_range"
    ] = [3, 5]
    refresh_binding(
        changed_range["all_rhs_records"]["1"]["modal_traction_positive"],
        1,
    )
    mutations.append(changed_range)
    for mutation in mutations:
        assert (
            authority._check_owner_packet_bindings(
                **mutation,
                bare_f_operator_hash="f" * 64,
            )
            is False
        )


def test_selected_builder_negative_column_applies_nonunit_mu() -> None:
    forward = np.asarray(
        [[0.0 + 0.0j], [0.0 + 0.0j], [0.0 + 0.0j]], dtype=np.complex128
    )
    backward = np.asarray(
        [[2.0 + 4.0j], [6.0 - 2.0j], [10.0 + 8.0j]], dtype=np.complex128
    )
    result = select_negative_bottom_backward_column(
        forward,
        backward,
        left_rows=1,
        right_rows=2,
        forward_factor=1.0 + 0.0j,
        backward_factor=2.0 - 1.0j,
    )
    np.testing.assert_allclose(
        result,
        np.asarray([(2.0 + 4.0j) / (2.0 - 1.0j)]),
    )


def test_selected_builder_initializes_one_cell_config_before_mesh(
    monkeypatch, tmp_path
):
    sentinel = RuntimeError("mesh builder sentinel")
    monkeypatch.setattr(
        one_cell_builder,
        "_one_cell_config",
        lambda _cfg, _size: SimpleNamespace(nedelec_degree=3),
    )
    monkeypatch.setattr(
        one_cell_builder,
        "build_airbox_mesh_3d",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(sentinel),
    )
    bottom_system = SimpleNamespace(
        side="bottom",
        static_condensation=object(),
        local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=MPI.COMM_SELF)),
    )
    with pytest.raises(RuntimeError, match="mesh builder sentinel"):
        one_cell_builder.build_exact_one_cell_selected_traction_columns(
            object(),
            {"positive": object(), "negative": object()},
            positive_beta=0.2 + 0.0j,
            negative_beta=-0.2 + 0.0j,
            positive_passive_branch_valid=True,
            negative_passive_branch_valid=True,
            bottom_system=bottom_system,
            work_dir=tmp_path,
        )


def test_optional_mpc_cleanup_is_capability_gated() -> None:
    no_destroy = SimpleNamespace(mpc=SimpleNamespace())
    assert one_cell_builder._cleanup_optional_mpc(no_destroy) == {
        "mpc_present": True,
        "destroy_called": False,
    }

    calls: list[int] = []

    class Destroyable:
        def destroy(self) -> None:
            calls.append(1)

    with_destroy = SimpleNamespace(mpc=Destroyable())
    assert one_cell_builder._cleanup_optional_mpc(with_destroy) == {
        "mpc_present": True,
        "destroy_called": True,
    }
    assert calls == [1]
    assert one_cell_builder._cleanup_optional_mpc(SimpleNamespace(mpc=None)) == {
        "mpc_present": False,
        "destroy_called": False,
    }
    assert one_cell_builder._cleanup_optional_mpc(None) == {
        "mpc_present": False,
        "destroy_called": False,
    }
