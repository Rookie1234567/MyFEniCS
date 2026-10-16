from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def test_y2_profile_binds_policy_through_direct_route_and_active_output_identity():
    from src.io.native_capacity_profile import (
        TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE,
        native_profile_facts,
    )
    from src.runners.p6_condensed_direct import (
        _direct_output_policy,
        _direct_run_contract,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        _active_fe_port_output_identity,
    )

    facts = native_profile_facts(TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE)
    options = facts["component_options"]
    assert options["dtn_sparse_cutoff_policy"] == "scale_homogeneous_relative_only_v1"
    assert options["dtn_sparse_cutoff_relative_tolerance"] == 1.0e-13

    route = _direct_run_contract(TASK40_PHI90_D13_Y2_P6_DIRECT_PROFILE)
    assert route["sparse_cutoff_policy"] == options["dtn_sparse_cutoff_policy"]
    assert route["sparse_cutoff_relative_tolerance"] == 1.0e-13
    assert route["direct_factor_evidence"]["pre_release"] is True
    assert len(route["direct_factor_evidence_mode_keys"]) == 6

    route.update(
        parent_count=612,
        active_count=612,
        parent_sha256="a" * 64,
        active_sha256="a" * 64,
        sparse_cutoff_identity_sha256="b" * 64,
    )
    output = _direct_output_policy(route)
    contract = output["active_fe_port_output_contract"]
    assert contract["schema"] == "task40.active_fe_port_outputs.v2"
    assert contract["dtn_sparse_cutoff_policy"] == route["sparse_cutoff_policy"]
    identity = _active_fe_port_output_identity(
        contract,
        active_mode_count=612,
        active_mode_sha256="a" * 64,
        sparse_cutoff_policy=route["sparse_cutoff_policy"],
        sparse_cutoff_relative_tolerance=route[
            "sparse_cutoff_relative_tolerance"
        ],
        sparse_cutoff_identity_sha256=route["sparse_cutoff_identity_sha256"],
    )
    assert identity["dtn_sparse_cutoff_identity_sha256"] == "b" * 64

    contract["dtn_sparse_cutoff_identity_sha256"] = "c" * 64
    with pytest.raises(ValueError, match="cutoff identity"):
        _active_fe_port_output_identity(
            contract,
            active_mode_count=612,
            active_mode_sha256="a" * 64,
            sparse_cutoff_policy=route["sparse_cutoff_policy"],
            sparse_cutoff_relative_tolerance=route[
                "sparse_cutoff_relative_tolerance"
            ],
            sparse_cutoff_identity_sha256=route[
                "sparse_cutoff_identity_sha256"
            ],
        )


def test_direct_factor_evidence_saves_only_requested_arrays_and_hashes(tmp_path):
    from src.runners.p6_condensed_direct import (
        _task40_exact_evidence_mode_indices,
        _write_task40_direct_factor_evidence,
    )

    keys = (
        ("top", -4, 0, "p"),
        ("top", 0, 0, "s"),
        ("top", 4, 0, "p"),
        ("bottom", -4, 0, "p"),
        ("bottom", 0, 0, "s"),
        ("bottom", 4, 0, "p"),
    )
    modes = [
        SimpleNamespace(side=side, m=m, n=n, polarization=pol)
        for side, m, n, pol in keys
    ]
    assert _task40_exact_evidence_mode_indices(modes, keys) == tuple(range(6))
    with pytest.raises(ValueError, match="misses evidence key"):
        _task40_exact_evidence_mode_indices(modes[:-1], keys)

    witness = {
        "status": "OBSERVED_NOT_QUALIFICATION",
        "orders": [{"side": key[0], "m": key[1], "n": key[2], "polarization": key[3]} for key in keys],
    }
    report = _write_task40_direct_factor_evidence(
        tmp_path,
        recovered_p6_storage=np.asarray([1 + 2j, 3 - 4j], dtype=np.complex128),
        retained_alpha=np.asarray([0.25 + 0.5j], dtype=np.complex128),
        modal_alpha=np.asarray([0.1j, -0.2j], dtype=np.complex128),
        schur_port_residual=np.asarray([1.0e-12j, 2.0e-12j], dtype=np.complex128),
        independent_port_residual=np.asarray([3.0e-13j, 4.0e-13j], dtype=np.complex128),
        active_rows=1,
        appended_rows=2,
        operator_identity={"mode_sha256": "a" * 64},
        factor_facts={"symbolic_calls": 1, "numeric_calls": 1, "solve_calls": 1},
        six_key_witness=witness,
    )
    assert report["status"] == "SAVED_PRE_RELEASE_NOT_QUALIFICATION"
    assert report["solver_qualification_claimed"] is False
    assert report["augmented_layout"]["retained_alpha_rows"] == [0, 1]
    assert report["augmented_layout"]["modal_alpha_rows"] == [1, 3]
    assert len(report["artifacts"]) == 5
    for artifact in report["artifacts"].values():
        path = tmp_path / "task40_direct_factor_evidence" / Path(artifact["path"]).name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
        assert np.load(path, allow_pickle=False).dtype == np.dtype(np.complex128)


def test_direct_factor_evidence_rejects_wrong_block_vector_shapes(tmp_path):
    from src.runners.p6_condensed_direct import _write_task40_direct_factor_evidence

    with pytest.raises(ValueError, match="layout is inconsistent"):
        _write_task40_direct_factor_evidence(
            tmp_path,
            recovered_p6_storage=np.ones(2, dtype=np.complex128),
            retained_alpha=np.ones(2, dtype=np.complex128),
            modal_alpha=np.ones(1, dtype=np.complex128),
            schur_port_residual=np.ones(1, dtype=np.complex128),
            independent_port_residual=np.ones(1, dtype=np.complex128),
            active_rows=1,
            appended_rows=1,
            operator_identity={},
            factor_facts={},
            six_key_witness={"orders": [1, 2, 3, 4, 5, 6]},
        )


def test_profile_policy_reaches_live_carrier_workspace_component_and_two_merge_stages(
    monkeypatch,
):
    from mpi4py import MPI

    import src.solvers.dtn_port_3d as dtn_port
    import src.solvers.fullspace_dtn_action as dtn_action
    from src.solvers.fullspace_dtn_action import FullspaceDtnCarrier

    policy = "scale_homogeneous_relative_only_v1"
    tolerance = 1.0e-13
    observed = {"workspace": [], "components": [], "merges": []}

    class SerialComm:
        def allreduce(self, value, op=None):
            return value

    class PetscComm:
        def tompi4py(self):
            return SerialComm()

    class Vector:
        def __init__(self, values):
            self.values = np.asarray(values, dtype=np.complex128)

        def getOwnershipRange(self):
            return 0, self.values.size

        def getArray(self, readonly=True):
            assert readonly
            return self.values

        def getComm(self):
            return PetscComm()

    class IndexMap:
        local_range = (0, 2)
        size_local = 2
        size_global = 2

        @staticmethod
        def local_to_global(rows):
            return np.asarray(rows, dtype=np.int32)

    mesh = SimpleNamespace(comm=MPI.COMM_SELF)
    function_space = SimpleNamespace(
        mesh=mesh,
        dofmap=SimpleNamespace(index_map=IndexMap(), index_map_bs=1),
    )
    mesh_data = SimpleNamespace(mesh=mesh)
    mpc = SimpleNamespace(
        function_space=function_space,
        slaves=np.asarray([], dtype=np.int32),
    )

    class Workspace:
        def __init__(
            self,
            _space,
            _mesh_data,
            _mpc,
            _assemblers,
            *,
            collect_timings,
            sparse_cutoff_policy,
            sparse_cutoff_relative_tolerance,
        ):
            assert not collect_timings
            self.sparse_cutoff_policy = sparse_cutoff_policy
            self.sparse_cutoff_relative_tolerance = sparse_cutoff_relative_tolerance
            self.owned_support = np.asarray([0, 1], dtype=np.int32)
            self.timing_totals = None
            self.facts = {
                "sparse_cutoff_policy": sparse_cutoff_policy,
                "sparse_cutoff_relative_tolerance": sparse_cutoff_relative_tolerance,
            }
            observed["workspace"].append((sparse_cutoff_policy, sparse_cutoff_relative_tolerance))

        def destroy(self):
            return None

    class Assembler:
        context = None
        surface_backend = None

        def __init__(self, component):
            self.component = component
            self.function_space = function_space
            self.mesh_data = mesh_data

        def assemble_entries(
            self,
            _mode,
            _mpc,
            *,
            workspace,
            sparse_cutoff_policy,
            sparse_cutoff_relative_tolerance,
        ):
            observed["components"].append(
                (self.component, sparse_cutoff_policy, sparse_cutoff_relative_tolerance)
            )
            values = (
                [2.0e-31 + 0j, 4.0e-44 + 0j]
                if self.component == 0
                else [1.0e-31 + 0j, -2.0e-44 + 0j]
            )
            return dtn_port._vec_nonzero_owned_entries(
                Vector(values),
                support=workspace.owned_support,
                sparse_cutoff_policy=sparse_cutoff_policy,
                relative_tol=sparse_cutoff_relative_tolerance,
            )

    assemblers = {
        (side, component): Assembler(component)
        for side in ("top", "bottom")
        for component in (0, 1)
    }
    mode = SimpleNamespace(
        side="top",
        m=0,
        n=0,
        polarization="s",
        alpha=0j,
        gamma=0j,
        beta=1 + 0j,
        refractive_index=1 + 0j,
        vertical_sign=1,
        e_vector=np.asarray([1 + 0j, 0.5j], dtype=np.complex128),
        k_vector=np.asarray([0j, 0j, 1 + 0j], dtype=np.complex128),
        h_vector=np.asarray([0j, 1 + 0j, 0j], dtype=np.complex128),
        electric_tangential_norm_sq=1.0,
        power_per_unit_amplitude=1.0,
        propagating=True,
        rayleigh_warning=False,
    )
    identity = {key: None for key in dtn_action._MODE_IDENTITY_FIELDS}
    identity.update(
        schema="fullspace-dtn.mode.v1",
        mode_index=0,
        side="top",
        m=0,
        n=0,
        polarization="s",
        alpha=0j,
        gamma=0j,
        beta=1 + 0j,
        k_vector=(0j, 0j, 1 + 0j),
        e_vector=(1 + 0j, 0.5j),
        h_vector=(0j, 1 + 0j, 0j),
        refractive_index=1 + 0j,
        vertical_sign=1,
        electric_tangential_norm_sq=1.0,
        power_per_unit_amplitude=1.0,
        propagating=True,
        rayleigh_warning=False,
        classification="propagating",
        rayleigh_tolerance=1.0e-12,
        projection_denominator=1.0,
        traction_vector=(1 + 0j, 0.25j),
    )
    monkeypatch.setattr(
        dtn_action,
        "build_ordered_mode_manifest",
        lambda *_args: ((identity,), b"manifest", "a" * 64),
    )
    monkeypatch.setattr(dtn_port, "_SurfaceMpcVectorWorkspace", Workspace)
    monkeypatch.setattr(dtn_port, "_mode_projection_denominator", lambda *_: 1.0)
    monkeypatch.setattr(dtn_port, "_traction_vector", lambda *_: (1 + 0j, 0.25j))
    original_merge = dtn_port._combine_owned_entries

    def merge_observer(*args, **kwargs):
        observed["merges"].append(
            (kwargs.get("sparse_cutoff_policy"), kwargs.get("relative_tol"))
        )
        return original_merge(*args, **kwargs)

    monkeypatch.setattr(dtn_port, "_combine_owned_entries", merge_observer)
    carrier = dtn_action.build_fullspace_dtn_carrier_from_surface(
        (mode,),
        assemblers,
        mpc,
        SimpleNamespace(diffraction_rayleigh_tol=1.0e-12),
        reuse_surface_vector=True,
        degree=6,
        sparse_cutoff_policy=policy,
        sparse_cutoff_relative_tolerance=tolerance,
        progress_interval=1,
    )

    assert observed["workspace"] == [(policy, tolerance)]
    assert observed["components"] == [
        (0, policy, tolerance),
        (1, policy, tolerance),
    ]
    assert observed["merges"] == [(policy, tolerance), (policy, tolerance)]
    assert carrier.audit["sparse_cutoff_policy"] == policy
    assert carrier.audit["sparse_cutoff_relative_tolerance"] == tolerance
    assert len(carrier.audit["sparse_cutoff_identity_sha256"]) == 64
    legacy_identity = FullspaceDtnCarrier(
        carrier.entries,
        global_rows=2,
        ownership_range=(0, 2),
        comm=MPI.COMM_SELF,
    )
    assert legacy_identity.mode_manifest_sha256 == carrier.mode_manifest_sha256
    assert (
        legacy_identity.audit["sparse_cutoff_identity_sha256"]
        != carrier.audit["sparse_cutoff_identity_sha256"]
    )

    with pytest.raises(ValueError, match="cannot use a persistent store"):
        dtn_action.build_fullspace_dtn_carrier_from_surface(
            (mode,),
            assemblers,
            mpc,
            SimpleNamespace(diffraction_rayleigh_tol=1.0e-12),
            reuse_surface_vector=True,
            degree=6,
            sparse_cutoff_policy=policy,
            sparse_cutoff_relative_tolerance=tolerance,
            functional_store_config={},
        )


def test_same_mesh_action_builder_carries_profile_policy_and_legacy_default(monkeypatch):
    from mpi4py import MPI

    import src.solvers.common_3d_forms as common_forms
    import src.solvers.dtn_port_3d as dtn_port
    import src.solvers.fullspace_dtn_action as dtn_action
    import src.solvers.fullspace_physical_action as physical_actions
    import src.solvers.fullspace_same_mesh_hcurl_pmg_physical as physical

    policy = "scale_homogeneous_relative_only_v1"
    tolerance = 1.0e-13
    observed = []
    mode = SimpleNamespace(side="top", m=0, n=0, polarization="s")
    rows = ({"mode_index": 0, "side": "top", "m": 0, "n": 0},)
    inventory = ((mode,), rows, "a" * 64)
    mesh = SimpleNamespace(comm=MPI.COMM_SELF)
    mesh_data = SimpleNamespace(mesh=mesh)
    mpc = object()
    setup = {
        "spaces": {6: object()},
        "floquets": {6: SimpleNamespace(mpc=mpc)},
        "mesh_data": mesh_data,
        "mesh": mesh,
    }
    cfg = SimpleNamespace()

    class OwnedAction:
        def destroy(self):
            return None

    class CompositeAction(OwnedAction):
        def __init__(self, volume, dtn):
            self.volume_action = volume
            self.dtn_action = dtn

    def build_carrier(*_args, **kwargs):
        active_policy = kwargs.get(
            "sparse_cutoff_policy", "absolute_floor_relative_v1"
        )
        active_tolerance = kwargs.get("sparse_cutoff_relative_tolerance", 1.0e-13)
        digest = hashlib.sha256(
            f"{active_policy}:{active_tolerance:.17g}".encode("ascii")
        ).hexdigest()
        carrier = SimpleNamespace(
            audit={"sparse_cutoff_identity_sha256": digest},
            sparse_cutoff_policy=active_policy,
            sparse_cutoff_relative_tolerance=active_tolerance,
        )
        observed.append((active_policy, active_tolerance))
        return carrier

    monkeypatch.setattr(common_forms, "_validate_physical_split_profile", lambda _cfg: None)
    monkeypatch.setattr(dtn_port, "_dtn_surface_quadrature_degree", lambda _cfg, _modes: 28)
    monkeypatch.setattr(dtn_port, "_incident_projection_onto_top_mode", lambda _mode, _cfg: 0j)
    monkeypatch.setattr(dtn_action, "build_fullspace_dtn_carrier_from_surface", build_carrier)
    monkeypatch.setattr(
        dtn_action,
        "build_fullspace_dtn_action",
        lambda carrier, *, comm: SimpleNamespace(carrier=carrier, comm=comm),
    )
    monkeypatch.setattr(physical, "_surface_assemblers", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        physical, "_build_split_volume_action", lambda *_args, **_kwargs: OwnedAction()
    )
    monkeypatch.setattr(physical_actions, "FullspacePhysicalAction", CompositeAction)

    task40_bundle = physical.build_same_mesh_physical_action(
        setup,
        cfg,
        6,
        mode_inventory=inventory,
        reuse_surface_vector=True,
        sparse_cutoff_policy=policy,
        sparse_cutoff_relative_tolerance=tolerance,
    )
    legacy_bundle = physical.build_same_mesh_physical_action(
        setup,
        cfg,
        6,
        mode_inventory=inventory,
        reuse_surface_vector=True,
    )

    assert observed == [
        (policy, tolerance),
        ("absolute_floor_relative_v1", 1.0e-13),
    ]
    assert task40_bundle["dtn_sparse_cutoff_policy"] == policy
    assert task40_bundle["dtn_sparse_cutoff_relative_tolerance"] == tolerance
    assert len(task40_bundle["dtn_sparse_cutoff_identity_sha256"]) == 64
    assert legacy_bundle["dtn_sparse_cutoff_policy"] == "absolute_floor_relative_v1"
    assert legacy_bundle["dtn_sparse_cutoff_relative_tolerance"] == 1.0e-13
