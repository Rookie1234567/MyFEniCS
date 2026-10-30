"""Opt-in scientific identity for raw affine constant-material volume tensors.

These tensors precede orientation, Floquet condensation, RHS and port phase.
Translation and incident/Bloch phase therefore do not enter this volume-only
identity. Actual canonical vertex coordinates and every compiled arithmetic
input do. No global matrix, local LU, port action or original residual is cached.
"""
from hashlib import sha256
import inspect
import math
import json
import os
from pathlib import Path
import sysconfig
import time

from ..common.exact_tensor_checkpoint import ExactTensorCheckpoint
from ..common.strict_json import snapshot


def _sha(path):
    h=sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()


def _lossless_unit_mu(value):
    if isinstance(value,bool) or not isinstance(value,(int,float,complex)):
        raise TypeError("explicit finite complex unit mu required")
    mu=complex(value)
    if not (math.isfinite(mu.real) and math.isfinite(mu.imag)) or mu.imag!=0 or mu.real!=1:
        raise ValueError("raw volume checkpoint only supports mu=1+0j")
    return float(mu.real)


class VolumeTensorCheckpoint:
    def __init__(self,cfg,directory,progress_path):
        from ..common.material_regions_3d import material_regions
        from dolfinx import jit
        mu_real=_lossless_unit_mu(cfg.mu_r)
        if cfg.grating_layer_thicknesses_nm is None or cfg.use_pml or float(cfg.divergence_penalty)!=0:
            raise ValueError('only explicit six-layer no-PML constant-material curl/mass profile')
        self.store=ExactTensorCheckpoint(directory)
        self.progress_path=Path(progress_path);self.receipts=[];self.compiled={}
        self.context={'schema':'raw-affine-constant-volume-scientific-identity.v1',
            'runtime_member_manifest_sha256':os.environ['TASK44_RUNTIME_MEMBER_MANIFEST_SHA256'],
            'compiler_policy_sha256':os.environ['TASK44_COMPILER_POLICY_SHA256'],
            'compiler_recipe_sha256':os.environ['TASK44_COMPILER_RECIPE_SHA256'],
            'active_CC':sysconfig.get_config_var('CC'),
            'cffi_extra_compile_args':list(jit.get_options()['cffi_extra_compile_args']),
            'k0_hex':float(cfg.k0).hex(),'mu_r_hex':mu_real.hex(),
            'material_regions':[{'tag':r.tag,'name':r.name,'epsilon_real_hex':float(r.epsilon_r.real).hex(),
                                 'epsilon_imag_hex':float(r.epsilon_r.imag).hex()} for r in material_regions(cfg)],
            'phase_and_translation_excluded_reason':'constant-material affine volume form only; fresh orientation/MPC/RHS/C-D/J and independent full UFL residual still required'}
        self.event({'stage':'raw_checkpoint_policy','context':self.context,'cache_directory':str(self.store.directory)})

    def event(self,value):
        row={'monotonic':time.monotonic(),**snapshot(value)}
        with self.progress_path.open('a') as f:
            f.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())

    def __call__(self,compiled_form,kernels,coordinates,tag,dimension,compute):
        import numpy as np
        from .hcurl_assembly_time_condensation import _tabulate_cell_tensor,_tabulate_raw_tensor_class
        from ..common.runtime_resource_policy import admit
        signature=compiled_form.module.ffi.string(compiled_form.ufcx_form.signature).decode('ascii')
        if signature not in self.compiled:
            shared=Path(compiled_form.module.__file__).resolve(strict=True)
            source=shared.with_name(shared.name.split('.cpython-',1)[0]+'.c')
            if shared.is_symlink() or source.is_symlink() or not source.is_file():raise RuntimeError('compiled raw volume C/SO identity')
            self.compiled[signature]={'ufcx_form_signature':signature,'compiled_C_sha256':_sha(source),
                'dimension':int(dimension),'dtype':str(np.dtype(compiled_form.dtype)),
                'basix_element_hash':int(compiled_form.function_spaces[0].element.basix_element.hash()),
                'kernel_ids_and_counts':[[int(k),len(v) if isinstance(v,(tuple,list)) else 1] for k,v in sorted(kernels.items())],
                'native_tabulation_source_sha256':sha256((inspect.getsource(_tabulate_cell_tensor)+inspect.getsource(_tabulate_raw_tensor_class)).encode()).hexdigest()}
            self.event({'stage':'compiled_raw_identity','identity':self.compiled[signature],
                        'execution_C':str(source),'execution_SO':str(shared),'execution_SO_sha256':_sha(shared)})
        identity={**self.context,'compiled':self.compiled[signature],'material_tag':int(tag),
                  'canonical_coordinate_dtype':'float64','canonical_coordinate_hex':[float(v).hex() for v in np.asarray(coordinates).ravel()],
                  'orientation_scope':'raw native vertex-order tensor before orientation; actual orientation applied freshly'}
        # Keep all currently retained classes in live RSS; this charge is only
        # the next full result plus a simultaneous native temporary and IO.
        admit('raw_volume_class_checkpoint',2*int(dimension)**2*16+4*2**20,
              estimate_basis={'tag':int(tag),'dimension':int(dimension),'cold_or_warm_same_reserve':True})
        self.event({'stage':'raw_class_begin','identity':identity})
        array,receipt=self.store.get_or_compute(identity,(int(dimension),int(dimension)),compute)
        self.receipts.append(receipt)
        self.event({'stage':'raw_class_committed','receipt':receipt})
        return array,receipt

    def verify(self):
        for receipt in self.receipts:
            for record in receipt['records']:
                p=Path(record['path'])
                if p.is_symlink() or p.stat().st_size!=record['bytes'] or _sha(p)!=record['sha256']:
                    raise RuntimeError('raw tensor checkpoint changed during assembly')
        self.event({'stage':'all_consumed_raw_checkpoints_unchanged','classes':len(self.receipts),
                    'cache_hits':sum(r['cache_hit'] for r in self.receipts),
                    'native_evaluations':sum(not r['cache_hit'] for r in self.receipts)})
