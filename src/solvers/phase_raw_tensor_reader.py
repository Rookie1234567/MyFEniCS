"""V54 opt-in read-only raw tensors, with exact mathematical dependencies.

The parent compiler signature binds the full Ckappa weak form. Its frozen
plan separately binds physical constants; no factor, Schur or port object is
reused. A missing/nonmatching class falls back to the original compiler.
"""
import hashlib
import json
import subprocess
import time
from pathlib import Path
import numpy as np
from .phase_tensor_checkpoint import RawTensorCheckpoint
from .scattering_anchor_checks import checked_arrays


class ReadonlyRawTensorProvider:
    def __init__(self,contracts,bundle,journal,root):
        self.bundle=bundle;self.journal=journal;self.root=Path(root)
        self.entries={};self.parents=[];self.hits=[];self.misses=[];self.seconds=0.
        for contract in contracts:
            path=self.root/contract['path']
            if hashlib.sha256(path.read_bytes()).hexdigest()!=contract['sha256']:
                raise ValueError('raw parent manifest hash')
            payload=json.loads(path.read_text());producer=payload['producer']
            if producer['source_sha']!=contract['source_sha']:raise ValueError('raw producer source')
            data=subprocess.check_output(['git','-c','gc.auto=0','-c','maintenance.auto=false','show',
                producer['source_sha']+':'+contract['plan_path']],cwd=self.root)
            if hashlib.sha256(data).hexdigest()!=producer['plan_sha256']:raise ValueError('raw frozen producer plan hash')
            plan=json.loads(data);physical=plan['physical_descriptor'];cfg=bundle['cfg']
            material=self.root/physical['materials']['canonical_table']
            if hashlib.sha256(material.read_bytes()).hexdigest()!=physical['materials']['sha256']:
                raise ValueError('raw material table hash')
            n=complex(*physical['materials']['Si_n']);inc=physical['incidence']
            if cfg.lambda0!=inc['wavelength_nm'] or cfg.eps_grating!=n*n or cfg.eps_substrate!=n*n or cfg.mu_r!=complex(*physical['materials']['mu_r']):
                raise ValueError('raw k0/epsilon/mu dependencies')
            from .fixed_phase_fem import carrier
            if not np.array_equal(carrier(cfg),bundle['kappa']):raise ValueError('raw live physical kappa')
            self.parents.append(dict(path=str(path),sha256=contract['sha256'],producer=producer['source_sha'],
                producer_plan_sha256=producer['plan_sha256'],physical=physical,
                constants=dict(k0=cfg.k0,epsilon=[n.real*n.real-n.imag*n.imag,2*n.real*n.imag],mu=[1.,0.]),
                basis_binding='full Basix element hash and compiled form signature include variant/map/order'))
            for entry in payload['classes']:
                if entry['degree']==bundle['degree']:self.entries.setdefault(entry['key'],[]).append((entry,contract))

    def load(self,form,coordinates,*,tag,dimension):
        key=RawTensorCheckpoint.key(coordinates,tag);signature=form.module.ffi.string(form.ufcx_form.signature).decode('ascii')
        for e,parent in self.entries.get(key,[]):
            if (e['dimension']!=dimension or e['dtype']!='complex128' or e['tag']!=int(tag) or
                e['element_hash']!=int(form.function_spaces[0].element.basix_element.hash()) or e['form_signature']!=signature or
                not np.array_equal(e['kappa'],self.bundle['kappa'])):continue
            began=time.perf_counter()
            with self.journal.measured('readonly_raw_tensor_hash_load'):
                values=checked_arrays(e['arrays'])
                if not np.array_equal(values['coordinates'],coordinates) or not np.array_equal(values['kappa'],self.bundle['kappa']):
                    raise ValueError('raw unrounded coordinates/carrier')
                tensor=values['tensor']
                if tensor.shape!=(dimension,dimension) or tensor.dtype!=np.complex128 or not np.isfinite(tensor).all():
                    raise ValueError('raw loaded shape/dtype/finite')
            elapsed=time.perf_counter()-began;self.seconds+=elapsed
            identity=dict(e,reused_parent=dict(manifest=parent['path'],sha256=parent['sha256'],
                producer=e['producer_sha'],load_seconds=elapsed),consumer_sha=self.journal.source_state['source_sha'])
            self.hits.append(dict(key=key,array_sha256=e['arrays']['sha256'],load_seconds=elapsed))
            return tensor,identity
        self.misses.append(key)
        self.journal.event('readonly_raw_class_missing_original_kernel_fallback',key=key)
        return None

    def record(self):
        return dict(parents=self.parents,hits=self.hits,misses=self.misses,hash_load_seconds=self.seconds,
            qualification='exact complete weak-form/basis/constant/geometry/material identity',
            cost_class='CACHE_REUSE_INCREMENTAL; parent preparation is not free cold N1')
