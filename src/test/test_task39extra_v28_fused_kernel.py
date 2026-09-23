"""Focused equivalence checks for the opt-in fused V28 local kernel."""

from contextlib import ExitStack
from collections.abc import Mapping
from types import SimpleNamespace

import numpy as np
from mpi4py import MPI
from dolfinx import fem, mesh
import dolfinx_mpc
import ufl

from src.solvers.fullspace_fused_split_volume import FullspaceFusedSplitVolumeAction
from src.solvers.fullspace_mpc_action import FullspaceMpcFormAction
from src.solvers.fullspace_partial_assembly import IsotropicPartialAssembly
from src.solvers.fullspace_physical_action import (
    FullspacePhysicalAction,
    FullspaceSplitVolumeAction,
)
from src.solvers.physical_equivalent_fast import build_packed_physical_action


def _physical_forms(space, domain, tags):
    from src.solvers.common_3d_forms import _build_physical_volume_terms

    cfg = SimpleNamespace(
        tags=SimpleNamespace(air=1, substrate=2, grating=3),
        mu_r=0.8,
        k0=1.3,
        eps_r=2.0 + 0.3j,
        substrate_index=np.sqrt(0.4 - 0.2j),
        grating_index=1.1 + 0.05j,
    )
    trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
    forms = _build_physical_volume_terms(
        cfg,
        trial,
        test,
        ufl.Measure("dx", domain=domain, subdomain_data=tags),
    )

    def with_degree(form, degree):
        return ufl.Form(
            tuple(
                integral.reconstruct(
                    metadata={
                        **integral.metadata(),
                        "quadrature_degree": degree,
                    }
                )
                for integral in form.integrals()
            )
        )

    return cfg, with_degree(forms[0], 4), with_degree(forms[1], 6)


def test_fused_split_volume_preserves_distinct_rules_and_full_action_semantics():
    domain = mesh.create_box(
        MPI.COMM_SELF,
        [np.zeros(3), np.array([1.0, 2.0, 3.0])],
        [9, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    domain.geometry.x[:, 0] = domain.geometry.x[:, 0] ** 2 + 0.1 * domain.geometry.x[:, 0]
    domain.geometry.x[:] = domain.geometry.x @ np.array(
        [[1.0, 0.2, -0.1], [0.0, 1.0, 0.3], [0.0, 0.0, 1.0]]
    )
    space = fem.functionspace(domain, ("N1curl", 2))
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.add_constraint(
        space,
        np.array([0], np.int32),
        np.array([1, 2], np.int64),
        np.array([0.25 + 0.5j, -0.1 + 0.2j]),
        np.array([0, 0], np.int32),
        np.array([0, 2], np.int32),
    )
    mpc.finalize()
    space = mpc.function_space
    tags = mesh.meshtags(
        domain,
        3,
        np.arange(9, dtype=np.int32),
        np.where(np.arange(9) % 2, 2, 1).astype(np.int32),
    )
    cfg, curl_form, mass_form = _physical_forms(space, domain, tags)
    dg = fem.functionspace(domain, ("DG", 0))
    mu, mass = fem.Function(dg), fem.Function(dg)
    mu.x.array[:] = 1.0 / cfg.mu_r
    mass.x.array[:] = np.where(
        np.arange(9) % 2,
        -cfg.substrate_index**2 * cfg.k0**2,
        -cfg.eps_r * cfg.k0**2,
    )
    mu.x.scatter_forward()
    mass.x.scatter_forward()
    kernels = tuple(
        IsotropicPartialAssembly(
            space,
            mu,
            mass,
            component_form=form,
            component=component,
            sum_factorized_work=True,
            shared_contractions=True,
        )
        for form, component in ((curl_form, "curl"), (mass_form, "mass"))
    )

    with ExitStack() as owned:
        curl_native = FullspaceMpcFormAction(
            curl_form, space, mpc=mpc, slave_row_identity=True
        )
        mass_native = FullspaceMpcFormAction(
            mass_form, space, mpc=mpc, slave_row_identity=False
        )
        owned.callback(curl_native.destroy)
        owned.callback(mass_native.destroy)
        legacy = FullspaceSplitVolumeAction(
            curl_form,
            mass_form,
            space,
            mpc=mpc,
            local_kernels=(
                IsotropicPartialAssembly(
                    space,
                    mu,
                    mass,
                    component_form=curl_form,
                    component="curl",
                    sum_factorized_work=True,
                ),
                IsotropicPartialAssembly(
                    space,
                    mu,
                    mass,
                    component_form=mass_form,
                    component="mass",
                    sum_factorized_work=True,
                ),
            ),
        )
        owned.callback(legacy.destroy)
        fused = FullspaceFusedSplitVolumeAction(
            curl_form,
            mass_form,
            space,
            mpc=mpc,
            local_kernels=kernels,
        )
        owned.callback(fused.destroy)
        source = curl_native.matrix.createVecRight()
        owned.callback(source.destroy)

        rng = np.random.default_rng(39028)
        for zero in (False, True):
            if zero:
                source.set(0.0)
            else:
                source.array[:] = rng.standard_normal(source.getLocalSize()) + 1j * rng.standard_normal(
                    source.getLocalSize()
                )
                source.array[0] = 0.7 - 0.2j
            source_before = source.array.copy()
            expected_curl = curl_native.apply(source).array.copy()
            expected_mass = mass_native.apply(source).array.copy()
            expected = expected_curl + expected_mass
            old = legacy.apply(source).array.copy()
            result = fused.apply(source)
            observed = result.array.copy()
            scale = max(np.linalg.norm(expected), np.finfo(float).tiny)
            assert np.linalg.norm(observed - expected) / scale <= 3.0e-11
            np.testing.assert_allclose(old, expected, rtol=3.0e-11, atol=3.0e-11)
            np.testing.assert_array_equal(source.array, source_before)
            if zero:
                np.testing.assert_array_equal(observed, np.zeros_like(observed))
            else:
                assert observed[int(mpc.slaves[0])] == source_before[int(mpc.slaves[0])]

        assert kernels[0].audit["quadrature_degree"] == 4
        assert kernels[1].audit["quadrature_degree"] == 6
        assert kernels[0].audit["points_sha256"] != kernels[1].audit["points_sha256"]
        assert fused.audit["constraint_identity_rows_exactly_once"] is True
        assert fused.audit["fused_local_kernel"]["gather_count"] == 4
        assert fused.audit["fused_local_kernel"]["coefficient_forward_count"] == 4
        assert fused.audit["fused_local_kernel"]["coefficient_backward_count"] == 4
        assert fused.audit["fused_local_kernel"]["scatter_count"] == 4
        assert (
            fused.audit["fused_local_kernel"]["unique_batch_workspace_bytes"]
            < fused.audit["fused_local_kernel"]["unique_scratch_and_cell_metadata_bytes_not_rss"]
        )

        # Component views remain available for profile pairing but borrow the
        # one shared output owner; each branch retains its original slave rule.
        expected_curl = curl_native.apply(source).array.copy()
        curl_view = fused.component_actions["curl"].apply(source)
        np.testing.assert_allclose(curl_view.array, expected_curl, rtol=3e-11, atol=3e-11)
        expected_mass = mass_native.apply(source).array.copy()
        mass_view = fused.component_actions["material_mass"].apply(source)
        np.testing.assert_allclose(mass_view.array, expected_mass, rtol=3e-11, atol=3e-11)

        class ZeroDtN:
            apply_count = 0

            def apply(self, _source, target):
                self.apply_count += 1
                target.set(0.0)

            def compose_physical_rhs(self, _base, _modes, target):
                target.set(0.0)

            @property
            def audit(self):
                return {"apply_count": self.apply_count}

            def destroy(self):
                return None

        dtn = ZeroDtN()
        full_action = FullspacePhysicalAction(fused, dtn, owns_dtn=False)
        target = source.duplicate()
        owned.callback(target.destroy)
        expected = curl_native.apply(source).array.copy() + mass_native.apply(source).array.copy()
        full_action.apply(source, target)
        np.testing.assert_allclose(target.array, expected, rtol=3e-11, atol=3e-11)
        assert dtn.apply_count == 1
        full_action.destroy()
        fused.destroy()
        with np.testing.assert_raises(RuntimeError):
            fused.apply(source)

    assert fused.audit["destroyed"] is True


def test_packed_factory_inventory_and_temporary_budget_follow_volume_owner():
    domain = mesh.create_box(
        MPI.COMM_SELF,
        [np.zeros(3), np.array([1.0, 1.0, 1.0])],
        [2, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    space = fem.functionspace(domain, ("N1curl", 2))
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.add_constraint(
        space,
        np.array([0], np.int32),
        np.array([1, 2], np.int64),
        np.array([0.25 + 0.5j, -0.1 + 0.2j]),
        np.array([0, 0], np.int32),
        np.array([0, 2], np.int32),
    )
    mpc.finalize()
    space = mpc.function_space
    tags = mesh.meshtags(
        domain,
        3,
        np.arange(2, dtype=np.int32),
        np.array([1, 2], dtype=np.int32),
    )
    cfg, curl_form, mass_form = _physical_forms(space, domain, tags)
    source_volume = FullspaceSplitVolumeAction(
        curl_form, mass_form, space, mpc=mpc
    )
    common = {
        "levels": {
            "floquets": {6: SimpleNamespace(mpc=mpc)},
            "mesh_data": SimpleNamespace(cell_tags=tags),
        },
        "fine": {
            "volume_action": source_volume,
            "dtn_action": SimpleNamespace(audit={}),
        },
    }

    with ExitStack() as owned:
        owned.callback(source_volume.destroy)
        for fuse_components, owner_count in ((False, 2), (True, 1)):
            candidate = build_packed_physical_action(
                common,
                cfg,
                fuse_components=fuse_components,
                sum_factorized_work=True,
                shared_contractions=False,
            )
            owned.callback(candidate["physical_action"].destroy)
            facts = candidate["facts"]

            # Exercise the same strict inventory extraction used by the p4
            # consumer, without building a p4 factor or Krylov workspace.
            inventory = {
                "material_function_array_bytes": int(
                    facts["material_function_array_bytes"]
                )
            }
            assert len(facts["component_audits"]) == owner_count
            for index, audit in enumerate(facts["component_audits"]):
                assert isinstance(audit, dict)
                components = audit["retained_numeric_payload_components"]
                assert isinstance(components, Mapping)
                for name, amount in components.items():
                    inventory[f"component_{index}_{name}"] = int(amount)
            assert len(inventory) > 1

            candidate_kernel_temporary_bytes = int(
                facts["kernel_temporary_bytes"]
            )
            if fuse_components:
                fused_owner = candidate["volume_action"].audit[
                    "shared_fullspace_mpc_action"
                ]
                assert dict(
                    facts["component_audits"][0][
                        "retained_numeric_payload_components"
                    ]
                ) == dict(fused_owner["retained_numeric_payload_components"])
                assert candidate_kernel_temporary_bytes == int(
                    facts["fused_volume_audit"]["temporary_budget_bytes"]
                )
                assert candidate_kernel_temporary_bytes == sum(
                    int(kernel["temporary_budget_bytes"])
                    for kernel in facts["kernels"]
                )
            else:
                split_budget = max(
                    int(kernel["temporary_budget_bytes"])
                    for kernel in facts["kernels"]
                )
                assert candidate_kernel_temporary_bytes == split_budget


def test_shared_tensor_dag_reuses_forward_prefixes_without_changing_result():
    domain = mesh.create_unit_cube(
        MPI.COMM_SELF, 2, 1, 1, cell_type=mesh.CellType.hexahedron
    )
    space = fem.functionspace(domain, ("N1curl", 2))
    dg = fem.functionspace(domain, ("DG", 0))
    mu, mass = fem.Function(dg), fem.Function(dg)
    mu.x.array[:] = 1.4
    mass.x.array[:] = 0.7
    legacy = IsotropicPartialAssembly(space, mu, mass, sum_factorized_work=True)
    shared = IsotropicPartialAssembly(
        space, mu, mass, sum_factorized_work=True, shared_contractions=True
    )
    old_sf, new_sf = legacy._sum_factorized, shared._sum_factorized
    count = 3
    rng = np.random.default_rng(39029)
    local = rng.standard_normal((count, space.element.space_dimension)) + 1j * rng.standard_normal(
        (count, space.element.space_dimension)
    )
    local[1] = 0.0
    local_before = local.copy()
    metrics = np.repeat(legacy.metrics[:1], count, axis=0)
    materials = np.column_stack(
        (
            np.full(count, mass.x.array[0], dtype=np.complex128),
            np.full(count, mu.x.array[0], dtype=np.complex128),
        )
    )
    expected = old_sf.apply(local, metrics, materials)
    observed = new_sf.apply(local, metrics, materials)
    observed_copy = observed.copy()
    np.testing.assert_allclose(observed, expected, rtol=3e-12, atol=3e-12)
    np.testing.assert_array_equal(local, local_before)
    assert old_sf.audit["forward_tensor_contraction_count"] == 27
    assert new_sf.audit["forward_tensor_contraction_count"] == 21
    assert old_sf.audit["backward_projection_count"] == 9
    assert new_sf.audit["backward_projection_count"] == 9
    assert new_sf.audit["backward_tensor_contraction_count"] == 27
    assert new_sf.audit["shared_contraction_scratch_bytes"] > 0

    # A fresh input after a zero batch must overwrite all reusable outputs.
    local[0] = 0.0
    np.testing.assert_allclose(new_sf.apply(local, metrics, materials)[0], 0.0, atol=1e-14)
    local[0] = local_before[2]
    repeated = new_sf.apply(local, metrics, materials)
    np.testing.assert_allclose(repeated[0], observed_copy[2], rtol=3e-12, atol=3e-12)
