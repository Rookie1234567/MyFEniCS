"""Bounded profile and isolated coordinate tests; no FE/JIT/factor/solve qualification."""
import ast
import importlib.util
from pathlib import Path
import sys
from dataclasses import replace

import numpy as np
import pytest

STAGED = Path(__file__).resolve().parents[1] / "solvers"
SPEC = importlib.util.spec_from_file_location("src.solvers.y_orbit_direct_profile", STAGED / "y_orbit_direct_profile.py")
PROFILE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PROFILE
SPEC.loader.exec_module(PROFILE)


def _physical_base():
    from src.common.config_3d import SimulationConfig3D
    s = PROFILE.SCALE
    return SimulationConfig3D(geometry_kind="rectangular_block_grating", lambda0=.7, incident_phi_deg=5,
        period_x=50*s, period_y=25*s, z_min=-10*s, z_max=130*s,
        grating_width_x=17*s, grating_width_y=25*s, grating_height=120*s)


@pytest.mark.parametrize("name,expected", [
    ("X", (120,25468,23808,12960,10848,2712,13236,11904,6480,5424,(2788,2864,2864,2864))),
    ("XZ", (168,35332,33024,18144,14880,3720,18364,16512,9072,7440,(3796,3872,3872,3872))),
    ("Y", (120,25468,23808,12960,10848,1808,8940,7936,4320,3616,(1884,1884,1884,1960,1884,1884))),
])
def test_exact_reviewed_integer_counts_and_actual_physical_inventory(name, expected):
    p = PROFILE.direct_profile_metadata(name)
    actual = (p.cell_count,p.storage_rows,p.independent_rows,p.interior_rows,p.trace_rows,p.trace_rows_per_q,
              p.local_storage_rows,p.local_independent_rows,p.local_interior_rows,p.local_trace_rows,p.augmented_rows_per_q)
    assert actual == expected
    cfg = PROFILE.build_direct_profile_config(_physical_base(), name)
    receipt = PROFILE.actual_direct_mode_inventory_counts(cfg, name)
    assert receipt["mode_count"] == 532
    assert receipt["q_port_counts"] == p.q_port_counts
    assert receipt["sector_port_counts"] == p.sector_port_counts
    assert p.factor_allowance_aggregate_bytes == (768 if name == "Y" else 512)*1024**2
    assert p.identity()["factor_fill_and_workspace"] is None
    assert cfg.incident_phi_deg == 5 and cfg.lambda0 == .7


@pytest.mark.parametrize("name", [None,"x","XZ6x4x7","same80","target",(6,4,5)])
def test_only_three_explicit_profiles_exist(name):
    with pytest.raises(ValueError): PROFILE.direct_profile_metadata(name)


@pytest.mark.parametrize("change", [dict(lambda0=13.5),dict(incident_phi_deg=0),dict(period_y=25),
    dict(grating_height=120),dict(cell_notch="notched"),dict(nedelec_trace_degree=3),
    dict(stage4_dtn_order_policy="auto_propagating"),dict(diffraction_order_max_n=0)])
def test_frozen_physical_and_full_element_contract_rejects_changes(change):
    cfg=PROFILE.build_direct_profile_config(_physical_base(), "X")
    with pytest.raises(ValueError): PROFILE.validate_direct_physical_config(replace(cfg,**change),"X")


def _class(file, name, directory=STAGED):
    tree=ast.parse((directory/file).read_text())
    node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==name)
    namespace={"np":np,"__package__":"src.solvers"}
    exec(compile(ast.Module(body=[node],type_ignores=[]),file,"exec"),namespace)
    return namespace[name]




class _NativeMomentCoordinates:
    def __init__(self,p,ny,bank):
        self.ny,self.width=ny,p.rows_per_q
        self.independent=np.arange(ny*self.width)
        self.full_rows=p.storage_rows if ny==p.ny else p.local_storage_rows
        self.dimension_counts={3:108*p.nx*ny*p.nz}
        self.bases=("complete_channels",);self.slots={"complete_channels":(0,self.width)}
        self.y_widths=np.diff(p.global_axes[1])[:ny]
        self._transform_bank=bank
        self.weights=(1.2+.1j)*np.ones(len(self.independent))
    def transform(self,v,*,direction):
        v=np.asarray(v);w=self.weights if v.ndim==1 else self.weights[:,None]
        if direction=="primal_to_canonical":return v/w
        if direction=="primal_from_canonical":return v*w
        if direction=="dual_to_canonical":return v*w.conj()
        if direction=="dual_from_canonical":return v/w.conj()
        if direction=="functional_to_canonical":return v*w
        if direction=="functional_from_canonical":return v/w
        raise ValueError(direction)


@pytest.mark.parametrize("name", ["X","XZ","Y"])
def test_all_K_strip_transport_nonunitary_pairing_and_all_twist_coverage(name):
    p=PROFILE.direct_profile_metadata(name);cfg=PROFILE.build_direct_profile_config(_physical_base(),name)
    bank=object();full=_NativeMomentCoordinates(p,p.ny,bank);local=_NativeMomentCoordinates(p,2,bank)
    T=_class("y_orbit_two_cell_transport.py","TwoCellNativeTransport")
    rng=np.random.default_rng(406532)
    u=rng.normal(size=p.local_independent_rows)+1j*rng.normal(size=p.local_independent_rows)
    b=rng.normal(size=p.independent_rows)+1j*rng.normal(size=p.independent_rows)
    sum_projection=np.zeros_like(b)
    for twist in range(p.replication_count):
        eta=np.exp(1j*(cfg.ky*cfg.period_y+2*np.pi*twist)/p.ny)
        t=T(full,local,twist_index=twist,eta=eta,global_phase=cfg.floquet_phase_y,
            global_ky=cfg.ky,global_period_y=cfg.period_y,direct_profile=name)
        assert t.K==p.replication_count and abs(t.tau**t.K-cfg.floquet_phase_y)<1e-12
        assert np.linalg.norm(t.extract_primal(t.lift_primal(u))-u)<1e-12*np.linalg.norm(u)
        lhs,rhs=np.vdot(b,t.lift_primal(u)),np.vdot(t.fold_dual(b),u)
        assert abs(lhs-rhs)<1e-12*max(abs(lhs),abs(rhs),1)
        assert np.linalg.norm(t.fold_raw_coupling(t.lift_raw_coupling(u))-u)<1e-12*np.linalg.norm(u)
        assert np.linalg.norm(t.fold_raw_projection(t.lift_raw_projection(u))-u)<1e-12*np.linalg.norm(u)
        sum_projection+=t.lift_primal(t.extract_primal(b))
    assert np.linalg.norm(sum_projection-b)<1e-12*np.linalg.norm(b)


@pytest.mark.parametrize("name", ["X","XZ","Y"])
def test_small_Ny_DFT_complete_primal_and_dual_coordinates(name):
    p=PROFILE.direct_profile_metadata(name);cfg=PROFILE.build_direct_profile_config(_physical_base(),name)
    entities=_NativeMomentCoordinates(p,p.ny,object())
    L=_class("y_orbit_two_cell_inverse.py","StreamedFullYLayout")(entities,cfg,direct_profile=name)
    rng=np.random.default_rng(406533);u=rng.normal(size=p.independent_rows)+1j*rng.normal(size=p.independent_rows)
    assert L.cell_dft.shape==(p.ny,p.ny)
    assert np.linalg.norm(L.primal_from_modal(L.primal_to_modal(u))-u)<1e-12*np.linalg.norm(u)
    modal=np.roll(u,1)
    lhs,rhs=np.vdot(u,L.primal_from_modal(modal)),np.vdot(L.dual_to_modal(u),modal)
    assert abs(lhs-rhs)<1e-12*max(abs(lhs),abs(rhs),1)


def test_metadata_has_no_numerical_execution_imports_and_factor_fill_remains_unknown():
    tree=ast.parse((STAGED/"y_orbit_direct_profile.py").read_text())
    imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert not any(name and any(s in name for s in ("dolfinx","petsc4py","hcurl_assembly")) for name in imports)
    inverse=ast.parse((STAGED/"y_orbit_two_cell_inverse.py").read_text())
    assert not any(isinstance(n,ast.Attribute) and n.attr in ("L","U") for n in ast.walk(inverse))
    source=(STAGED/"y_orbit_two_cell_inverse.py").read_text()
    assert "factor_workspace_allowance_bytes=remaining" in source
    assert "LU_fill_and_workspace_unknown=True" in source
