"""Actual two-cell setup through the new runner's owning factor context."""

from types import SimpleNamespace

import dolfinx_mpc
import numpy as np
import pytest
import ufl
from petsc4py import PETSc

from src.runners.physical_p4_cell_condensed_v18 import cell_condensed_stack
from src.test.test_115_task035b_assembly_time_condensation import _two_cell_problem


class TinyRuntime:
    def __init__(self):
        self.contract = {"resources": {"local_factor_matrix_and_allocated_cap_bytes": 6 << 30,
                                       "interface_matrix_factor_solve_cap_bytes": 6 << 30}}
        self.inventory = {}
        self.workspace = {}
        self.events = []

    def marker(self, name, facts):
        self.events.append((name, facts))

    def set_phase(self, phase):
        self.events.append(("phase", phase))

    def sample(self, label):
        return {"rss_bytes": 1, "label": label}

    def check_projected(self, _label, amount, *, workspace_bytes=0):
        assert 0 <= amount < 8 << 30
        assert 0 <= workspace_bytes < 1 << 30

    def check_inventory_projected(self, _label, amount):
        assert sum(sum(c.values()) for c in self.inventory.values()) + amount <= 6 << 30

    def reserve_inventory(self, label, components, *, check_rss=True):
        self.inventory[label] = dict(components)
        assert sum(sum(c.values()) for c in self.inventory.values()) <= 6 << 30

    def release_inventory(self, label):
        self.inventory.pop(label, None)

    def reserve_workspace(self, label, amount):
        self.workspace[label] = amount
        assert sum(self.workspace.values()) <= 1 << 30

    def release_workspace(self, label):
        self.workspace.pop(label, None)


@pytest.mark.parametrize("raise_in_context", [False, True])
def test_actual_stack_preallocation_factor_apply_and_cleanup(raise_in_context):
    domain, tags, space, _compiled = _two_cell_problem(distinct_materials=False)
    u, v = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=domain, subdomain_data=tags)
    form = (ufl.inner(ufl.curl(u), ufl.curl(v))
            + (2.5 - .2j) * ufl.inner(u, v)) * dx(1)
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.finalize()
    floquet = SimpleNamespace(mpc=mpc)
    n = space.dofmap.index_map.size_global
    entry = SimpleNamespace(coupling_rows=np.array([], dtype=PETSc.IntType),
                            coupling_values=np.array([], complex),
                            projection_rows=np.array([], dtype=PETSc.IntType),
                            projection_values=np.array([], complex), normalization_h=1.)
    carrier = SimpleNamespace(entries=(entry,), global_rows=n)
    common = {"levels": {"mesh": domain, "mesh_data": SimpleNamespace(cell_tags=tags),
                          "spaces": {4: space, 6: space}, "floquets": {4: floquet, 6: floquet}},
              "p4": {"volume_action": SimpleNamespace(bilinear_form=form),
                     "dtn_action": SimpleNamespace(carrier=carrier)},
              "fine": {"mode_sha256": "m" * 64, "dtn_action": SimpleNamespace(carrier=carrier)},
              "quadrature": [{"quadrature_degree": 4}, {"quadrature_degree": 4}]}
    runtime = TinyRuntime()
    captured = None
    try:
        with cell_condensed_stack(runtime, common, {}, stage="U0_FIXTURE") as stack:
            captured = stack
            assert stack["factor"].numeric_calls == 1
            rhs = PETSc.Vec().createSeq(n)
            rhs.set(1)
            try:
                result, facts = stack["fint"].apply_with_facts(rhs)
                assert facts["factor_solve_count"] == 1
                assert np.isfinite(result.array).all()
                result.destroy()
            finally:
                rhs.destroy()
            if raise_in_context:
                raise RuntimeError("fixture context failure")
    except RuntimeError as exc:
        if not raise_in_context or str(exc) != "fixture context failure":
            raise
    assert captured is not None
    assert captured["inverse"].destroyed
    assert captured["factor"].destroyed
    assert captured["condensed"].matrix.handle == 0
    assert not captured["condensed"].interior_lu_by_class
    assert runtime.inventory == runtime.workspace == {}
    assert any(name == "schur_factor_numeric_complete" for name, _ in runtime.events)
