"""Real p2/h50 serial smoke for the N1 local-cell adapter."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest
import ufl
import numpy as np
from dolfinx import fem
from mpi4py import MPI

from src.solvers.fullspace_local_spectral_dolfinx import (
    _canonical_row_expansions,
    _class_digest,
    _mpc_expansion,
    _prepare_real_context,
    _relative,
    _relative_canonical_row_descriptor,
    build_real_local_regional_rayleigh_ritz,
    build_real_local_spectral_patches,
    small_p2p3_local_action_oracle,
)
from src.solvers.hcurl_affine_isotropic_tensor import (
    AffineIsotropicMaxwellTensorFactory,
    AffineIsotropicMaxwellTensorSpec,
)
from src.test.test_280_task038_fullspace_trace_harmonic import (
    _constrained_dense,
    _real_fixture,
)


EXPECTED_P2_MPI1_REGION_CELL_COUNTS = (8, 4, 4, 2, 4, 2, 2, 1)
# These source/action digests are the serial authority only after the
# independent constrained-UFL action below and the independent repeat both
# pass.  They are not regional projector identities.
EXPECTED_P2_MPI1_ORACLE_SOURCE_DIGEST = (
    "ba7d2b3a184fb9a30b36aaee641e594f1ba05c2c0af15d144c4960f235531bcf"
)
EXPECTED_P2_MPI1_ORACLE_ACTION_DIGEST = (
    "5e9836a197c0dd3a7420a9c230e9a0b3afd78e205060e70eb01e3983d949dc5a"
)
EXPECTED_P2_MPI1_ORACLE_IDENTITY = (
    "c55c2a56bff2389410201518c1450a767061dce85743e8eca83143d8cba65e4e"
)


def _regional_identity(audit):
    payload = (
        audit["canonical_patch_mode_digests"],
        audit["regional_expanded_mode_digests"],
        audit["source_action_digests"],
        audit["regional_ranks"],
        audit["regional_candidate_m_ranks"],
    )
    return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


def _canonical_values_digest(values_by_key):
    keys = tuple(sorted(values_by_key, key=repr))
    payload = tuple(
        (
            repr(key),
            (float(values_by_key[key].real), float(values_by_key[key].imag)),
        )
        for key in keys
    )
    return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


def _small_oracle_identity(source_by_key, action_by_key):
    return hashlib.sha256(
        repr(
            (
                _canonical_values_digest(source_by_key),
                _canonical_values_digest(action_by_key),
            )
        ).encode("utf-8")
    ).hexdigest()


def _merge_small_oracle_packets(packets):
    source_by_key = {}
    action_by_key = {}
    for packet in packets:
        for key, value in packet["canonical_source"].items():
            if key in source_by_key and source_by_key[key] != value:
                raise AssertionError(f"source value differs for canonical key {key!r}")
            source_by_key[key] = value
        for key, value in packet["local_action_by_key"].items():
            action_by_key[key] = action_by_key.get(key, 0.0j) + value
    if tuple(sorted(source_by_key, key=repr)) != tuple(sorted(action_by_key, key=repr)):
        raise AssertionError("canonical source/action key sets differ")
    return source_by_key, action_by_key


def _canonical_cell_action(packets):
    cells = {}
    for packet in packets:
        for cell_key, values in packet["cell_action_by_key"].items():
            if cell_key in cells:
                raise AssertionError(f"duplicate canonical cell {cell_key!r}")
            cells[cell_key] = values
    result = {}
    for cell_key in sorted(cells, key=repr):
        for key, value in cells[cell_key].items():
            result[key] = result.get(key, 0.0j) + value
    return result


def test_small_oracle_key_closure_rejects_extra_or_missing_packets():
    base = {
        "canonical_source": {"owned": 1.0 + 0.0j},
        "local_action_by_key": {"owned": 2.0 + 0.0j},
    }
    with pytest.raises(AssertionError, match="key sets differ"):
        _merge_small_oracle_packets(
            [
                base,
                {
                    "canonical_source": {"owned": 1.0 + 0.0j},
                    "local_action_by_key": {
                        "owned": 2.0 + 0.0j,
                        "ghost_only": 3.0 + 0.0j,
                    },
                },
            ]
        )
    with pytest.raises(AssertionError, match="key sets differ"):
        _merge_small_oracle_packets(
            [
                base,
                {
                    "canonical_source": {
                        "owned": 1.0 + 0.0j,
                        "missing_action": 4.0 + 0.0j,
                    },
                    "local_action_by_key": {"owned": 2.0 + 0.0j},
                },
            ]
        )


@pytest.mark.parametrize("degree", [2])
def test_real_p2_h50_local_cell_tensor_mpc_smoke(tmp_path, degree):
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("the first real local-cell adapter smoke is serial-only")
    cfg, mesh_data, _raw_space, space, floquet_data, _topology = _real_fixture(
        tmp_path, degree
    )
    patches, audit = build_real_local_spectral_patches(
        space, mesh_data, floquet_data, cfg
    )
    oracle = small_p2p3_local_action_oracle(
        space, mesh_data, floquet_data, cfg
    )
    print(
        "REAL_LOCAL_SMALL_ORACLE_IDENTITIES",
        {
            "source": _canonical_values_digest(oracle["canonical_source"]),
            "action": _canonical_values_digest(oracle["local_action_by_key"]),
            "source_action": _small_oracle_identity(
                oracle["canonical_source"], oracle["local_action_by_key"]
            ),
            "source_keys": len(oracle["canonical_source"]),
        },
        flush=True,
    )
    assert _canonical_values_digest(oracle["canonical_source"]) == (
        EXPECTED_P2_MPI1_ORACLE_SOURCE_DIGEST
    )
    assert _canonical_values_digest(oracle["local_action_by_key"]) == (
        EXPECTED_P2_MPI1_ORACLE_ACTION_DIGEST
    )
    assert _small_oracle_identity(
        oracle["canonical_source"], oracle["local_action_by_key"]
    ) == EXPECTED_P2_MPI1_ORACLE_IDENTITY
    trial = ufl.TrialFunction(_raw_space)
    test = ufl.TestFunction(_raw_space)
    dx = ufl.Measure(
        "dx", domain=_raw_space.mesh, subdomain_data=mesh_data.cell_tags
    )
    form = (
        (1.0 / complex(cfg.mu_r))
        * ufl.inner(ufl.curl(trial), ufl.curl(test))
        * dx
    )
    for tag, epsilon in (
        (cfg.tags.air, cfg.eps_air),
        (cfg.tags.substrate, cfg.eps_substrate),
        (cfg.tags.grating, cfg.eps_grating),
    ):
        form += (
            cfg.k0**2
            * abs(epsilon)
            * ufl.inner(trial, test)
            * dx(int(tag))
        )
    assembled_constrained, assembled_free_rows = _constrained_dense(
        form, _raw_space, space, floquet_data.mpc
    )
    scale_context = _prepare_real_context(space, mesh_data, floquet_data, cfg)
    source = np.asarray(
        [oracle["source_by_raw_row"][int(row)] for row in assembled_free_rows],
        dtype=np.complex128,
    )
    assembled_action = assembled_constrained @ source
    assembled_by_key = {}
    for row, value in zip(assembled_free_rows, assembled_action, strict=True):
        row = int(row)
        key = oracle["raw_to_key"][row]
        if key in assembled_by_key:
            raise AssertionError(f"duplicate assembled canonical key {key!r}")
        assembled_by_key[key] = np.conj(scale_context["raw_to_scale"][row]) * value
    keys = tuple(sorted(oracle["local_action_by_key"], key=repr))
    local_values = np.asarray(
        [oracle["local_action_by_key"][key] for key in keys],
        dtype=np.complex128,
    )
    assembled_values = np.asarray(
        [assembled_by_key[key] for key in keys], dtype=np.complex128
    )
    assembled_relative_error = float(
        np.linalg.norm(local_values - assembled_values)
        / max(np.linalg.norm(assembled_values), 1.0e-300)
    )
    del assembled_constrained, assembled_action, source, form, dx, trial, test
    audit["independent_global_assembled_oracle"] = {
        "kind": "small_assembled_oracle_only",
        "relative_error": assembled_relative_error,
        "limit": 1.0e-11,
        "passed": assembled_relative_error <= 1.0e-11,
        "global_object_destroyed": True,
        "production_path_references_oracle": oracle["production_path_references_oracle"],
    }
    print(
        "REAL_LOCAL_SPECTRAL_SMOKE_METRICS",
        {key: audit[key] for key in (
            "cell_count",
            "patch_count",
            "row_count_min",
            "row_count_max",
            "class_count",
            "owner_factor_count",
            "owner_factor_bytes",
            "B0_hermitian_relative_defect",
            "M_local_hermitian_relative_defect",
            "B0_min_eigenvalue",
            "M_local_min_eigenvalue",
            "gradient_rank_min",
            "gradient_m_gram_relative_defect_max",
            "projected_eigen_residual_max",
            "fixed_solve_residual_max",
            "pou_closure_relative_error",
            "restriction_prolongation_adjoint_relative_error_max",
            "dense_workspace_released",
            "independent_global_assembled_oracle",
            "mode_digest",
        )},
        flush=True,
    )
    assert audit["cell_count"] == audit["patch_count"] == 27
    assert 0 < audit["row_count_min"] <= audit["row_count_max"] <= 882
    assert 0 < audit["class_count"] <= 32
    assert audit["owner_factor_count"] == audit["class_count"]
    assert audit["global_owner_factor_count"] == audit["class_count"]
    assert audit["owner_factor_bytes"] > 0
    assert audit["B0_hermitian_relative_defect"] <= 1.0e-11
    assert audit["M_local_hermitian_relative_defect"] <= 1.0e-11
    assert audit["B0_min_eigenvalue"] > 0.0
    assert audit["M_local_min_eigenvalue"] > 0.0
    assert audit["gradient_rank_min"] == 3
    assert audit["gradient_m_gram_relative_defect_max"] <= 1.0e-11
    assert audit["projected_eigen_residual_max"] <= 1.0e-11
    assert audit["fixed_solve_residual_max"] <= 1.0e-11
    assert audit["pou_closure_relative_error"] <= 1.0e-13
    assert audit["pou_closure_route"] == (
        "owner_local_fem_function_scatter_reverse_insert_add"
    )
    assert audit["restriction_prolongation_adjoint_relative_error_max"] <= 1.0e-13
    assert audit["dense_workspace_released"] is True
    assert audit["independent_global_assembled_oracle"]["passed"] is True
    assert audit["independent_global_assembled_oracle"]["relative_error"] <= 1.0e-11
    assert audit["independent_global_assembled_oracle"]["global_object_destroyed"] is True
    assert audit["production_path_references_oracle"] is False
    assert audit["imported_master_metadata"] == {
        "local_missing_count": 0,
        "global_request_count": 0,
        "global_resolved_count": 0,
        "global_unresolved_count": 0,
    }
    assert audit["gradient_definition"].endswith("finalized MPC homogenize/backsubstitution")
    assert audit["forbidden_objects"] == {
        "global_numeric_allgather": False,
        "global_aij": False,
        "global_schur": False,
        "static_condensation": False,
        "trace_harmonic_backend": False,
        "per_patch_retained_dense_block": False,
    }
    assert all(
        patch.audit["phase_application"]
        == "maximum_amplitude_canonical_key_once_tie_by_key"
        for patch in patches
    )
    assert all(patch.audit["construction_workspace_released"] for patch in patches)

    regional, regional_audit, multilevel = build_real_local_regional_rayleigh_ritz(
        patches, space, mesh_data, floquet_data, cfg, return_multilevel=True
    )
    assert regional_audit["macroregion_rule"] == (
        "canonical_lower_cell_index_integer_division_by_2"
    )
    assert regional_audit["region_count"] > 0
    assert regional_audit["global_cell_count"] == 27
    assert regional_audit["max_region_cell_count"] <= 8
    assert regional_audit["region_cell_counts"] == EXPECTED_P2_MPI1_REGION_CELL_COUNTS
    assert all(1 <= rank <= 16 for rank in regional_audit["regional_ranks"])
    assert regional_audit["regional_mass_orthogonality_max"] <= 1.0e-11
    assert regional_audit["regional_projected_eigen_residual_max"] <= 1.0e-11
    assert audit["pou_closure_relative_error"] <= 1.0e-13
    assert audit["pou_closure_route"] == (
        "owner_local_fem_function_scatter_reverse_insert_add"
    )
    assert regional_audit["top_rank_built"] is True
    assert regional_audit["multilevel_basis_built"] is True
    assert multilevel.audit["top_rank"] == 32
    assert multilevel.audit["regional_rank"] == 16
    assert multilevel.audit["regional_columns_semantics"] == (
        "fixed_global_sum_of_same_regional_mode_index_rank16"
    )
    assert multilevel.audit["top_columns_semantics"] == (
        "region_distinguished_fixed_sha256_mix_rank32"
    )
    assert multilevel.audit["global_direct_coarse_solve"] is False
    assert multilevel.audit["top_orthogonality_relative_defect"] <= 1.0e-11
    context = _prepare_real_context(space, mesh_data, floquet_data, cfg)
    owned_rows = int(space.dofmap.index_map.size_local)
    assert multilevel.columns.shape[0] == owned_rows
    assert multilevel.audit["row_order"] == (
        "physical_dofmap_owned_local_order"
    )
    assert multilevel.audit["physical_owned_rows"] == owned_rows
    assert "active_row_positions" not in multilevel.audit
    assert multilevel.audit["active_row_position_count"] == len(
        multilevel.row_keys
    )
    assert len(multilevel.audit["active_row_positions_sha256"]) == 64
    assert multilevel.audit["canonical_key_scatter"] == (
        "hash_owner_staging_to_dofmap_owned_local_order"
    )
    field = fem.Function(space)
    field.x.array[:owned_rows] = multilevel.columns[:, 0]
    field.x.scatter_forward()
    observed = {}
    for raw_row, key in context["raw_to_key"].items():
        raw_row = int(raw_row)
        if raw_row >= owned_rows or raw_row in context["slave_rows"]:
            continue
        if key in observed:
            raise AssertionError(f"canonical key repeated in owned rows: {key!r}")
        observed[key] = complex(field.x.array[raw_row])
    expected = {
        key: complex(multilevel.columns[int(position), 0])
        for key, position in zip(
            multilevel.row_keys,
            multilevel.active_row_positions,
            strict=True,
        )
    }
    assert tuple(sorted(observed, key=repr)) == tuple(sorted(expected, key=repr))
    assert _relative(
        np.asarray(
            [observed[key] - expected[key] for key in sorted(expected, key=repr)],
            dtype=np.complex128,
        ),
        np.asarray(
            [expected[key] for key in sorted(expected, key=repr)],
            dtype=np.complex128,
        ),
    ) <= 1.0e-12
    del field, context
    assert regional_audit["contraction_not_run"] is True
    assert regional_audit["regional_dense_row_operator_materialized"] is False
    assert regional_audit["max_candidate_dimension"] <= 64
    assert regional_audit["max_projected_dimension"] <= 64
    assert regional_audit["streamed_region_count"] == regional_audit["region_count"]
    assert all(
        item["source_independent"] and item["selected_rank"] <= 16
        and item["regional_dense_row_operator_materialized"] is False
        for item in regional.values()
    )
    print(
        "REAL_LOCAL_REGIONAL_METRICS",
        {
            "region_count": regional_audit["region_count"],
            "regional_ranks": regional_audit["regional_ranks"],
            "candidate_m_ranks": regional_audit["regional_candidate_m_ranks"],
            "mass_orthogonality": regional_audit[
                "regional_mass_orthogonality_max"
            ],
            "projected_residual": regional_audit[
                "regional_projected_eigen_residual_max"
            ],
            "max_candidate_dimension": regional_audit["max_candidate_dimension"],
            "max_projected_dimension": regional_audit["max_projected_dimension"],
        },
        flush=True,
    )
    print(
        "REAL_LOCAL_REGIONAL_DIGESTS",
        {
            "patch": regional_audit["canonical_patch_mode_digests"],
            "expanded": regional_audit["regional_expanded_mode_digests"],
            "source_action": regional_audit["source_action_digests"],
            "identity": _regional_identity(regional_audit),
        },
        flush=True,
    )
    # The former bitwise regional identity was a raw-coordinate comparator
    # artifact.  Regional expanded projector/packet differences are retained
    # as diagnostics; hard MPI identity is the canonical full-space
    # source/action comparison in the formal checker.  Per-case mode order and
    # phase are decided by the exact repeat below.
    assert regional_audit["regional_projected_eigen_residual_max"] <= 1.0e-11

    first_digest = audit["mode_digest"]
    class_plan = patches[0].class_plan
    for patch in patches:
        patch.destroy()
    class_plan.destroy()
    multilevel.destroy()

    repeat_patches, repeat_audit = build_real_local_spectral_patches(
        space, mesh_data, floquet_data, cfg
    )
    assert repeat_audit["mode_digest"] == first_digest
    assert repeat_audit["pou_closure_relative_error"] <= 1.0e-13
    assert repeat_audit["restriction_prolongation_adjoint_relative_error_max"] <= 1.0e-13
    for patch in repeat_patches:
        patch.destroy()


def test_real_p2_h50_class_template_setup_smoke(tmp_path):
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("class-template setup smoke is serial-only")
    cfg, mesh_data, _raw_space, space, floquet_data, _topology = _real_fixture(
        tmp_path, 2
    )
    patches, audit = build_real_local_spectral_patches(
        space,
        mesh_data,
        floquet_data,
        cfg,
        reuse_class_templates=True,
    )
    assert audit["degree"] == 2
    assert audit["mode_template_count"] == audit["class_count"]
    assert audit["class_template_eigensolve"] == (
        "one canonical representative per exact class"
    )
    assert audit["global_owner_factor_count"] == audit["class_count"]
    assert audit["global_owner_factor_bytes"] == audit["owner_factor_bytes"]
    assert audit["mode_shard_bytes_retained_global"] == sum(
        patch.modes.nbytes for patch in patches
    )
    assert audit["dense_workspace_released"] is True
    assert all(patch.audit["mode_template_reused"] for patch in patches)
    assert all(patch.block is None and patch.local_mass is None for patch in patches)
    class_plan = patches[0].class_plan
    for patch in patches:
        patch.destroy()
    class_plan.destroy()
    assert class_plan.factor_count == 0
    assert class_plan.factor_bytes == 0


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="distributed regional p2 smoke requires MPI2",
)
def test_real_p2_h50_distributed_regional_identity(tmp_path):
    cfg, mesh_data, _raw_space, space, floquet_data, _topology = _real_fixture(
        tmp_path, 2
    )
    patches, patch_audit = build_real_local_spectral_patches(
        space, mesh_data, floquet_data, cfg
    )
    regional, regional_audit, multilevel = build_real_local_regional_rayleigh_ritz(
        patches, space, mesh_data, floquet_data, cfg, return_multilevel=True
    )
    comm = MPI.COMM_WORLD
    identity = _regional_identity(regional_audit)
    assert patch_audit["global_owner_factor_count"] == patch_audit["class_count"]
    imported_metadata = patch_audit["imported_master_metadata"]
    assert imported_metadata["global_request_count"] > 0
    assert imported_metadata["global_resolved_count"] == (
        imported_metadata["global_request_count"]
    )
    assert imported_metadata["global_unresolved_count"] == 0
    assert comm.allreduce(
        imported_metadata["local_missing_count"], op=MPI.SUM
    ) > 0
    assert comm.allreduce(patch_audit["owner_factor_count"], op=MPI.SUM) == (
        patch_audit["class_count"]
    )
    local_classes = comm.allgather(set(patch_audit["local_class_digests"]))
    nonlocal_representatives = tuple(
        (digest, owner)
        for digest, owner in patch_audit["class_owners"].items()
        if digest not in local_classes[owner]
    )
    assert nonlocal_representatives
    if comm.rank == 0:
        print(
            "REAL_LOCAL_CLASS_OWNER_NONLOCAL",
            nonlocal_representatives[0],
            flush=True,
        )
    for region, participants in regional_audit["region_participants"].items():
        owner = regional_audit["region_owners"][region]
        assert owner in participants
    assert regional_audit["max_candidate_dimension"] <= 64
    assert regional_audit["max_projected_dimension"] <= 64
    assert regional_audit["regional_dense_row_operator_materialized"] is False
    assert regional_audit["regional_mass_orthogonality_max"] <= 1.0e-11
    assert regional_audit["regional_projected_eigen_residual_max"] <= 1.0e-11
    assert len(regional) == regional_audit["region_count"]
    assert multilevel.audit["top_rank"] == 32
    assert multilevel.audit["regional_rank"] == 16
    assert multilevel.audit["global_numeric_allgather"] is False
    assert multilevel.audit["regional_columns_semantics"] == (
        "fixed_global_sum_of_same_regional_mode_index_rank16"
    )
    assert multilevel.audit["top_columns_semantics"] == (
        "region_distinguished_fixed_sha256_mix_rank32"
    )
    assert multilevel.audit["global_direct_coarse_solve"] is False
    assert multilevel.audit["top_orthogonality_relative_defect"] <= 1.0e-11
    context = _prepare_real_context(space, mesh_data, floquet_data, cfg)
    owned_rows = int(space.dofmap.index_map.size_local)
    assert multilevel.columns.shape[0] == owned_rows
    assert multilevel.audit["row_order"] == (
        "physical_dofmap_owned_local_order"
    )
    assert multilevel.audit["physical_owned_rows"] == owned_rows
    field = fem.Function(space)
    field.x.array[:owned_rows] = multilevel.columns[:, 0]
    field.x.scatter_forward()
    observed = {}
    for raw_row, key in context["raw_to_key"].items():
        raw_row = int(raw_row)
        if raw_row >= owned_rows or raw_row in context["slave_rows"]:
            continue
        if key in observed:
            raise AssertionError(f"canonical key repeated in owned rows: {key!r}")
        observed[key] = complex(field.x.array[raw_row])
    expected = {
        key: complex(multilevel.columns[int(position), 0])
        for key, position in zip(
            multilevel.row_keys,
            multilevel.active_row_positions,
            strict=True,
        )
    }
    assert tuple(sorted(observed, key=repr)) == tuple(sorted(expected, key=repr))
    assert _relative(
        np.asarray(
            [observed[key] - expected[key] for key in sorted(expected, key=repr)],
            dtype=np.complex128,
        ),
        np.asarray(
            [expected[key] for key in sorted(expected, key=repr)],
            dtype=np.complex128,
        ),
    ) <= 1.0e-12
    del field, context
    # This is only rank-local consistency.  The MPI1/MPI2 Gate is the
    # numerical canonical packet comparison from the focused diagnostic, not
    # equality to a serial hash.
    assert len(set(comm.allgather(identity))) == 1
    assert regional_audit["global_cell_count"] == 27
    assert regional_audit["max_region_cell_count"] <= 8
    assert regional_audit["region_cell_counts"] == EXPECTED_P2_MPI1_REGION_CELL_COUNTS
    assert len(
        set(comm.allgather(regional_audit["canonical_cell_inventory_digest"]))
    ) == 1

    oracle = small_p2p3_local_action_oracle(
        space, mesh_data, floquet_data, cfg
    )
    oracle_packets = comm.gather(
        {
            "canonical_source": oracle["canonical_source"],
            "local_action_by_key": oracle["local_action_by_key"],
            "cell_action_by_key": oracle["cell_action_by_key"],
        },
        root=0,
    )
    if comm.rank == 0:
        merged_source, merged_action = _merge_small_oracle_packets(oracle_packets)
        canonical_action = _canonical_cell_action(oracle_packets)
        keys = tuple(sorted(merged_action, key=repr))
        merged_values = np.asarray(
            [merged_action[key] for key in keys], dtype=np.complex128
        )
        canonical_values = np.asarray(
            [canonical_action[key] for key in keys], dtype=np.complex128
        )
        action_relative = float(
            np.linalg.norm(merged_values - canonical_values)
            / max(np.linalg.norm(canonical_values), 1.0e-300)
        )
        oracle_identity = (
            _canonical_values_digest(merged_source),
            _canonical_values_digest(merged_action),
            _small_oracle_identity(merged_source, merged_action),
            action_relative,
        )
        print(
            "REAL_LOCAL_MPI2_SMALL_ORACLE",
            {
                "source": oracle_identity[0],
                "action": oracle_identity[1],
                "source_action": oracle_identity[2],
                "action_relative": oracle_identity[3],
                "packet_count": len(oracle_packets),
                "kind": "small_assembled_oracle_only",
            },
            flush=True,
        )
    else:
        oracle_identity = None
    oracle_identity = comm.bcast(oracle_identity, root=0)
    assert oracle_identity[0] == EXPECTED_P2_MPI1_ORACLE_SOURCE_DIGEST
    assert oracle_identity[3] <= 1.0e-12
    if comm.rank == 0:
        print("REAL_LOCAL_REGIONAL_MPI2_IDENTITY", identity, flush=True)
    class_plan = patches[0].class_plan
    for patch in patches:
        patch.destroy()
    class_plan.destroy()
    multilevel.destroy()


def test_affine_mass_tensor_matches_zero_curl_tensor(tmp_path):
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("the affine mass API focused test is serial-only")
    cfg, _mesh_data, _raw_space, space, _floquet_data, _topology = _real_fixture(
        tmp_path, 2
    )
    factory = AffineIsotropicMaxwellTensorFactory(
        space.element.basix_element,
        AffineIsotropicMaxwellTensorSpec(
            curl_coefficient=0.0j,
            mass_coefficient_by_tag={
                int(cfg.tags.air): complex(cfg.k0**2 * abs(cfg.eps_air))
            },
        ),
    )
    tensor = factory.tensor(tag=int(cfg.tags.air), widths=(25.0, 25.0, 25.0))
    mass = factory.mass_tensor(
        tag=int(cfg.tags.air), widths=(25.0, 25.0, 25.0)
    )
    assert np.array_equal(tensor, mass)


def test_primal_dual_diagonal_scale_pairing_contract():
    rng = np.random.default_rng(380)
    raw_matrix = rng.normal(size=(7, 7)) + 1j * rng.normal(size=(7, 7))
    raw_scale = rng.normal(size=7) + 1j * rng.normal(size=7)
    raw_scale += 1.0 + 0.5j
    primal = rng.normal(size=7) + 1j * rng.normal(size=7)
    dual_test = rng.normal(size=7) + 1j * rng.normal(size=7)
    scale = np.diag(raw_scale)
    canonical_matrix = scale.conj().T @ raw_matrix @ scale
    left = np.vdot(dual_test, canonical_matrix @ primal)
    right = np.vdot(scale @ dual_test, raw_matrix @ (scale @ primal))
    relative = abs(left - right) / max(abs(right), 1.0e-300)
    assert relative <= 1.0e-13


def test_real_adapter_has_no_global_matrix_or_condensation_backend():
    path = Path(__file__).parents[1] / "solvers" / "fullspace_local_spectral_dolfinx.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert "src.solvers.hcurl_assembly_time_condensation" not in imported
    forbidden = {"assemble_matrix", "createAIJ", "allgather"}
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not calls & forbidden
    assert source.count("AffineIsotropicMaxwellTensorFactory(") == 1
    assert ".mass_tensor(" in source


def test_canonical_expansion_preserves_local_row_association():
    from src.solvers.hcurl_canonical_vector import canonical_key

    element = SimpleNamespace(
        hash=lambda: 287,
        degree=2,
        cell_type=SimpleNamespace(name="hexahedron"),
    )
    cfg = SimpleNamespace(mu_r=1.0)

    def build_case(
        *,
        translation=(0, 0, 0),
        raw_ids=(101, 202),
        tag=1,
        widths=(1.0, 1.0, 1.0),
        first_scale=1.0 + 0.0j,
        second_point_offset=(0, 1, 0),
    ):
        origin = tuple(int(value) for value in translation)
        first_entity = (
            origin,
            tuple(origin[axis] + (1 if axis == 0 else 0) for axis in range(3)),
        )
        second_entity = (
            origin,
            tuple(
                origin[axis] + int(second_point_offset[axis])
                for axis in range(3)
            ),
        )
        raw_to_key = {
            int(raw_ids[0]): canonical_key(
                role="full_fe",
                entity_dimension=1,
                physical_entity=first_entity,
                entity_local_basis_index=0,
                orientation_state=("edge", 0),
            ),
            int(raw_ids[1]): canonical_key(
                role="full_fe",
                entity_dimension=1,
                physical_entity=second_entity,
                entity_local_basis_index=1,
                orientation_state=("edge", 1),
            ),
        }
        raw_to_scale = {
            int(raw_ids[0]): complex(first_scale),
            int(raw_ids[1]): 1.0 + 0.0j,
        }
        local_dofs = np.asarray(raw_ids, dtype=np.int32)
        no_constraint_mpc = SimpleNamespace(
            coefficients=lambda: (
                np.asarray([], dtype=np.complex128),
                np.asarray([0, 0, 0], dtype=np.int64),
            )
        )
        free_rows, sparse_pattern, _expansion_pattern = _mpc_expansion(
            local_dofs,
            no_constraint_mpc,
            set(),
            raw_to_key,
            raw_to_scale,
        )
        local_descriptors = tuple(
            _relative_canonical_row_descriptor(raw_to_key[int(row)], origin)
            for row in local_dofs
        )
        free_descriptors = tuple(
            _relative_canonical_row_descriptor(raw_to_key[int(row)], origin)
            for row in free_rows
        )
        return {
            "canonical_row_expansions": _canonical_row_expansions(
                local_descriptors,
                free_descriptors,
                tuple(raw_to_scale[int(row)] for row in local_dofs),
                sparse_pattern,
            ),
            "digest": _class_digest(
                element=element,
                cfg=cfg,
                tag=tag,
                widths=widths,
                canonical_row_expansions=_canonical_row_expansions(
                    local_descriptors,
                    free_descriptors,
                    tuple(raw_to_scale[int(row)] for row in local_dofs),
                    sparse_pattern,
                ),
            ),
            "expansion": sparse_pattern,
        }

    first = build_case()
    translated_and_relabelled = build_case(
        translation=(100, -40, 17), raw_ids=(303, 404)
    )
    assert first["digest"] == translated_and_relabelled["digest"]

    changed_tag = build_case(tag=2)
    changed_width = build_case(widths=(2.0, 1.0, 1.0))
    changed_topology = build_case(second_point_offset=(0, 0, 1))
    row_descriptor, row_expansion = first["canonical_row_expansions"][0]
    changed_coefficient_expansion = tuple(
        (free_descriptor, [coefficient[0] + 0.25, coefficient[1]])
        for free_descriptor, coefficient in row_expansion
    )
    changed_coefficient_payload = tuple(
        [(row_descriptor, changed_coefficient_expansion)]
        + list(first["canonical_row_expansions"][1:])
    )
    changed_coefficient_digest = _class_digest(
        element=element,
        cfg=cfg,
        tag=1,
        widths=(1.0, 1.0, 1.0),
        canonical_row_expansions=changed_coefficient_payload,
    )
    assert len({
        changed_tag["digest"],
        changed_width["digest"],
        changed_coefficient_digest,
        changed_topology["digest"],
    }) == 4
