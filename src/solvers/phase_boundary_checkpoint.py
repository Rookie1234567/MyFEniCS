"""Study-local exact surface components; independent quadratures stay distinct.

Only immutable coefficients are reloaded. Live mesh/basis/MPC/mode/carrier
identities must match before any assembler can consume the packet.
"""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from src.runners.task042_shared import write_json,_json_metadata
from .scattering_anchor import save_arrays,relative
from .scattering_anchor_checks import checked_arrays


def digest(value):
    return hashlib.sha256(json.dumps(_json_metadata(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def wave_key(mode):
    return (mode.side,complex(mode.alpha),complex(mode.gamma),complex(mode.k_vector[2]))


def packed_action(v,x,*,adjoint=False):
    """Literal CD/H action, also usable on old independent packed witnesses."""
    y=np.zeros_like(x,dtype=complex)
    for i,h in enumerate(v['H']):
        sl=slice(v['offsets'][i],v['offsets'][i+1]);rows=v['rows'][sl];c=v['C'][sl];d=v['D'][sl]
        if adjoint:np.add.at(y,rows,np.conj(d)*np.vdot(c,x[rows])/np.conj(h))
        else:np.add.at(y,rows,c*np.dot(d,x[rows])/h)
    return y


class LoadedSurface:
    def __init__(self,receipt,space,mpc,cfg,q,kappa,identity):
        p=Path(receipt);row=json.loads(p.read_text())
        if row['identity']!=identity:raise ValueError('surface live identity mismatch')
        v=checked_arrays(row['arrays']);off=v['component_offsets'];n=int(identity['native_rows'])
        if len(off)!=len(row['keys'])+1 or off[0]!=0 or off[-1]!=len(v['component_rows']) or np.any(np.diff(off)<0):raise ValueError('surface component inventory')
        if v['component_values'].shape!=(len(v['component_rows']),2) or v['incident'].shape!=(n,):raise ValueError('surface payload shape')
        if np.any(v['component_rows']<0) or np.any(v['component_rows']>=n) or any(not np.all(np.isfinite(a)) for a in v.values()):raise ValueError('surface finite/rows')
        self.space,self.mpc,self.cfg,self.q=space,mpc,cfg,q
        self.method=row['method'];self.phase_carrier=np.asarray(kappa);self.seconds=0.;self.calls=0;self.receipt=row
        self.incident=v['incident'];self.cache={}
        for i,key in enumerate(row['keys']):
            sl=slice(off[i],off[i+1]);rr=v['component_rows'][sl];vv=v['component_values'][sl]
            if np.any(np.diff(rr)<=0):raise ValueError('surface duplicate/noncanonical rows')
            self.cache[digest(key)]=(rr,vv)

    def components(self,mode):
        key=digest(wave_key(mode))
        if key not in self.cache:raise ValueError('surface mode or incident inventory absent')
        return self.cache[key]

    def assemblers(self):
        parent=self
        class Component:
            def __init__(self,j):self.j=j
            def assemble_entries(self,mode,mpc):
                if mpc is not parent.mpc:raise ValueError('live surface MPC object')
                rows,v=parent.components(mode);return rows,v[:,self.j]
        return {(s,j):Component(j) for s in ('top','bottom') for j in (0,1)}

    def incident_traction(self):return self.incident.copy()


class StudyBoundaryProvider:
    def __init__(self,cfg,setup,folder,journal,*,entity_face_support=False):
        from .fullspace_dtn_action import build_dynamic_mode_inventory
        self.cfg,self.setup,self.folder,self.journal=cfg,setup,Path(folder)/'boundary_packets',journal
        self.folder.mkdir(parents=True,exist_ok=True);self.V=setup['spaces'][cfg.nedelec_degree]
        self.mpc=setup['floquets'][cfg.nedelec_degree].mpc;self.k=np.asarray(setup['numerical_carrier'])
        self.modes,self.ids,self.mode_sha=build_dynamic_mode_inventory(cfg)
        self.generated={};self.loads={}
        self.entity_face_support=bool(entity_face_support)

    def identity(self,q):
        import basix
        from .target_boundary_witness import dual_maps
        from src.postprocessing.phase_volume_quadrature import array_hash
        V=self.V;m=V.mesh;mpc=self.mpc;m.topology.create_entity_permutations();maps=dual_maps(V,mpc)
        counts=np.asarray([len(r) for r,_ in maps]);rows=np.concatenate([r for r,_ in maps]);dual=np.concatenate([c for _,c in maps])
        pts,w=basix.make_quadrature(basix.CellType.quadrilateral,q)
        value=dict(schema='study.exact.boundary.v1',q=q,method='separable' if q==47 else 'basix2d',
            native_rows=V.dofmap.index_map.size_local,ownership=[0,V.dofmap.index_map.size_global],MPI=m.comm.size,
            geometry=array_hash(m.geometry.x),geometry_dofmap=array_hash(m.geometry.dofmap),
            native_cell_dofs=array_hash(np.asarray([V.dofmap.cell_dofs(c) for c in range(len(m.geometry.dofmap))])),
            permutations=array_hash(m.topology.get_cell_permutation_info()),
            facet_indices=array_hash(self.setup['mesh_data'].facet_tags.indices),facet_tags=array_hash(self.setup['mesh_data'].facet_tags.values),
            basis_hash=int(V.element.basix_element.hash()),basis=array_hash(V.element.basix_element.coefficient_matrix),
            MPC_counts=array_hash(counts),MPC_rows=array_hash(rows),MPC_complex_dual=array_hash(dual),
            mode_sha256=self.mode_sha,complete_modes=len(self.modes),physical_mode_rows=digest(self.ids),
            reference_planes=[self.cfg.z_bottom,self.cfg.z_top] if hasattr(self.cfg,'z_bottom') else [self.cfg.z_min,self.cfg.z_max],
            kappa=self.k.tolist(),incident=digest(dict(k=self.cfg.wavevector,e=self.cfg.polarization_vector,a=self.cfg.incident_amplitude)),
            points=array_hash(pts),weights=array_hash(w),producer_source=self.journal.source_state['source_sha'],
            component_module_sha256=hashlib.sha256(Path(__file__).with_name('scattering_accuracy_boundary.py').read_bytes()).hexdigest(),
            checkpoint_module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        if self.entity_face_support:value['entity_face_support']=True
        return value

    def load(self,q):
        with self.journal.measured(f'boundary_packet_reload_q{q}'):
            out=LoadedSurface(self.folder/f'q{q}.json',self.V,self.mpc,self.cfg,q,self.k,self.identity(q))
        self.loads[q]=self.loads.get(q,0)+1
        return out

    def bundle(self,q):
        from .fullspace_dtn_action import build_fullspace_dtn_carrier_from_surface
        from .dtn_port_3d import _incident_projection_onto_top_mode
        src=self.load(q)
        c=build_fullspace_dtn_carrier_from_surface(self.modes,src.assemblers(),self.mpc,self.cfg,retain_all_nonzero=True)
        return dict(cfg=self.cfg,setup=self.setup,degree=self.cfg.nedelec_degree,kappa=self.k,
            modes=self.modes,mode_rows=self.ids,mode_sha256=self.mode_sha,
            incident_projections=tuple(_incident_projection_onto_top_mode(m,self.cfg) for m in self.modes),
            dtn_action=SimpleNamespace(carrier=c),dtn_quadrature_degree=q,surface=src)

    def generate_pair(self):
        from .scattering_accuracy_boundary import SurfaceComponents,pack_carrier,carrier_pair
        from .fullspace_dtn_action import build_fullspace_dtn_carrier_from_surface
        objects=[];receipts=[];inc=[];costs=[]
        for q,method in ((47,'separable'),(63,'basix2d')):
            path=self.folder/f'q{q}.json'
            if path.exists():raise RuntimeError('boundary packet already generated: reload, never repeat integration')
            with self.journal.measured(f'one_original_boundary_generation_q{q}'):
                src=SurfaceComponents(self.V,self.mpc,self.cfg,q,method=method,phase_carrier=self.k,entity_face_support=self.entity_face_support)
                c=build_fullspace_dtn_carrier_from_surface(self.modes,src.assemblers(),self.mpc,self.cfg,retain_all_nonzero=True)
                incident=src.incident_traction();keys=list(src.cache);offset=[0];rr=[];vv=[]
                for key in keys:
                    r,v=src.cache[key];rr.append(r);vv.append(v);offset.append(offset[-1]+len(r))
                receipt=save_arrays(self.folder/f'q{q}.npz',**pack_carrier(c),incident=incident,
                    component_offsets=np.asarray(offset,np.int64),component_rows=np.concatenate(rr),component_values=np.concatenate(vv))
                record=dict(identity=self.identity(q),method=method,keys=_json_metadata(keys),arrays=receipt,
                    producer=self.journal.source_state,seconds=src.seconds,unique_wavevectors=src.calls)
                if self.entity_face_support:record['structural_zeros']=dict(topology_defined=True,maximum=src.structural_zero_max,operation_scale=src.structural_zero_scale)
                write_json(path,record);self.generated[q]=1;costs.append(src.seconds);inc.append(incident)
            objects.append(c);receipts.append(receipt)
            # Independent reload before any production consumer is allowed.
            loaded=self.bundle(q)['dtn_action'].carrier
            paired=carrier_pair(c,loaded,self.ids,expected_modes=len(self.modes))
            if not paired['pass']:raise ValueError('original/reloaded full boundary differ')
            del src,loaded
        pair=carrier_pair(*objects,self.ids,expected_modes=len(self.modes));rng=np.random.default_rng(58047)
        x=rng.normal(size=self.V.dofmap.index_map.size_local)+1j*rng.normal(size=self.V.dofmap.index_map.size_local);x[self.mpc.slaves]=0
        packed=[checked_arrays(r) for r in receipts];actions=[packed_action(v,x) for v in packed];ad=[packed_action(v,x,adjoint=True) for v in packed]
        forward=relative(actions[0]-actions[1],actions[1]);adjoint=relative(ad[0]-ad[1],ad[1]);incident=relative(inc[0]-inc[1],inc[1])
        witness=save_arrays(self.folder/'action_pair.npz',input=x,forward47=actions[0],forward63=actions[1],adjoint47=ad[0],adjoint63=ad[1],incident47=inc[0],incident63=inc[1])
        r=dict(pair=pair,forward=forward,adjoint=adjoint,incident=incident,arrays=receipts,witness=witness,
            mode_sha256=self.mode_sha,degree=self.cfg.nedelec_degree,costs=costs,pass_gate=pair['pass'] and max(forward,adjoint)<=1e-10 and incident<=1e-11,
            provider_folder=str(self.folder),generated=dict(self.generated),q47_not_q63=True)
        write_json(self.folder/'qualification.json',r);self.journal.calls['A']+=2;self.journal.calls['AH']+=2
        return r
