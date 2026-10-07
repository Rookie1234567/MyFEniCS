"""Narrow V60 readonly preparation resume, with live physical identities.

The previous actor's file hashes are frozen after its safe stop. Saved child
and macro factors are reused; redundant construction arrays are not resident.
"""
import hashlib
import json
from pathlib import Path
import numpy as np
from .scattering_anchor import array_hash
from .scattering_anchor_checks import checked_arrays
from .subcell_response_kernel import ChildBlock,MacroResponse
from .fixed_phase_fem import carrier


def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def complex_value(value):return complex(value['real'],value['imag'])


class LazyPhaseTable:
    def __init__(self,V,cfg,journal):
        self.element=V.element.basix_element;self.kappa=carrier(cfg);self.k0=cfg.k0;self.mu=cfg.mu_r
        self.epsilon={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating}
        self.backend='AFFINE_PHASE_REFERENCE_TENSOR';self.table=None;self.V=V;self.cfg=cfg;self.journal=journal
    def tensor(self,*,tag,widths):
        if self.table is None:
            from .subcell_macro_response import factory
            self.table=factory(self.V,self.cfg,self.journal)
        return self.table.tensor(tag=tag,widths=widths)


class FrozenSubcellPreparation:
    def __init__(self,inventory,journal,table):
        self.journal=journal;self.table=table;self.children={};self.macros={};self.child_hits=0;self.macro_hits=0
        path=Path(inventory);record=json.loads(path.read_text());self.binding=dict(path=str(path),sha256=file_hash(path),producer=record['producer'])
        if record['producer']!='d728fbc7113531af4dbc3d0f3655e1d05246fa1e':raise ValueError('V60 fixed stopped preparation producer')
        from .local_subcell_scope import PLAN
        if record['plan_sha256']!=file_hash(PLAN):raise ValueError('saved preparation physical/space plan changed')
        for name,value in record['unchanged_math'].items():
            if file_hash(Path(PLAN).parents[2]/name)!=value:raise ValueError('saved preparation numerical dependency changed')
        for item in record['children']:
            p=Path(item['metadata_path'])
            if file_hash(p)!=item['metadata_sha256']:raise ValueError('child preparation metadata identity')
            r=json.loads(p.read_text())
            if r['producer']!=record['producer'] or r['degree']!=table.element.degree or r['element_hash']!=int(table.element.hash()) or r['k0']!=table.k0 or complex_value(r['mu'])!=table.mu or complex_value(r['epsilon'])!=table.epsilon[r['tag']]:raise ValueError('child preparation live basis/physical identity')
            key=(r['tag'],r['permutation'],r['arrays']['members']['widths']['sha256'])
            if key in self.children:raise ValueError('duplicate saved child identity')
            self.children[key]=r
        for item in record['macros']:
            p=Path(item['metadata_path'])
            if file_hash(p)!=item['metadata_sha256']:raise ValueError('macro preparation metadata identity')
            r=json.loads(p.read_text());key=(r['key'],r['tag'])
            if key in self.macros:raise ValueError('duplicate saved macro identity')
            self.macros[key]=(r,item['arrays'])
        journal.event('readonly_partial_preparation_inventory_bound',**self.binding,child_inventory=len(self.children),macro_inventory=len(self.macros),hashes_frozen_after_stop=True)
    def child(self,tag,widths,permutation):
        row=self.children.get((int(tag),int(permutation),array_hash(widths)))
        if row is None:return None
        a=checked_arrays(row['arrays'])
        if not np.array_equal(a['widths'],widths) or not np.array_equal(a['kappa'],self.table.kappa):raise ValueError('saved child exact widths/carrier')
        with self.journal.measured('saved_child_factor_read_and_qualification'):result=ChildBlock.from_checkpoint(a,self.table.element)
        self.child_hits+=1;return result
    def macro(self,layout,tag,blocks):
        pair=self.macros.get((layout.key,int(tag)))
        if pair is None:return None
        metadata,receipt=pair;a=checked_arrays(receipt)
        with self.journal.measured('saved_macro_factor_read_no_new_LU'):result=MacroResponse.from_checkpoint(layout,blocks,a,metadata['capacity'])
        self.macro_hits+=1;return result,receipt
    def record(self):return dict(self.binding,child_hits=self.child_hits,macro_hits=self.macro_hits,reused_factor_not_rebuilt=True,
        redundant_child_raw_residency=False,macro_response_column_residency=False,previous_failure_cost_preserved=True)


def freeze_stopped_preparation():
    """Bound only the stopped V60 partial case, never scan prior campaigns."""
    import os
    from . import local_subcell_scope as scope
    from src.runners.task042_shared import write_json
    scope.window.guard_worker_parent();producer='d728fbc7113531af4dbc3d0f3655e1d05246fa1e'
    runs=[r for r in scope.window.ledger()['runs'] if r['role']=='H2' and r['source_sha']==producer]
    if len(runs)!=1 or runs[0]['classification']!='WORKER_FAILED':raise ValueError('one stopped H2 preparation inventory')
    parent=scope.ARTIFACT/Path(runs[0]['folder']).name;manifest=Path(runs[0]['folder'])/'run_manifest.json'
    bound=json.loads(manifest.read_text())
    if bound['source_sha']!=producer or bound['scope']!='v60' or bound['plan_sha256']!=file_hash(scope.PLAN):raise ValueError('stopped parent live case binding')
    names=('src/solvers/hcurl_affine_phase_tensor.py','src/solvers/hcurl_affine_isotropic_tensor.py','src/solvers/fixed_phase_fem.py','src/solvers/local_trace_assembly.py')
    unchanged={n:bound['implementation_hashes'][n] for n in names}
    children=[];macros=[]
    for p in sorted((parent/'child_complete_packets').glob('*.json')):
        r=json.loads(p.read_text())
        if r['producer']!=producer:raise ValueError('stopped child producer')
        if file_hash(r['arrays']['path'])!=r['arrays']['sha256']:raise ValueError('stopped child byte hash')
        children.append(dict(metadata_path=str(p),metadata_sha256=file_hash(p)))
    for p in sorted((parent/'local_response_packets').glob('*.json')):
        packet=p.with_suffix('.npz');members={}
        with np.load(packet,allow_pickle=False) as a:
            for name in a.files:
                v=a[name];members[name]=dict(shape=list(v.shape),dtype=str(v.dtype),sha256=array_hash(v))
        receipt=dict(path=str(packet),sha256=file_hash(packet),members=members)
        macros.append(dict(metadata_path=str(p),metadata_sha256=file_hash(p),arrays=receipt))
    record=dict(schema='v60.stopped-subcell-preparation.v1',producer=producer,parent_run_manifest=dict(path=str(manifest),sha256=file_hash(manifest)),
        plan_sha256=bound['plan_sha256'],unchanged_math=unchanged,children=children,macros=macros,
        frozen_after_stopped_actor=True,old_files_not_modified=True,missing_classes_constructed_once=True,new_factor_count=0)
    path=scope.window.TMP/'H2_preparation_resume.json';write_json(path,record)
    write_json(Path(os.environ['TASK042_V36_AUX_DIRECTORY'])/'preparation_snapshot_receipt.json',dict(path=str(path),sha256=file_hash(path),child_classes=len(children),macro_classes=len(macros),new_global_factors=0))


if __name__=='__main__':freeze_stopped_preparation()
