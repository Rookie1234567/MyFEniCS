"""RawTensorCheckpoint reader protocol, producing complete phase tensors."""
import numpy as np
from .hcurl_affine_phase_tensor import AffinePhaseReferenceTensor,axis_widths
from .phase_tensor_checkpoint import RawTensorCheckpoint
from .scattering_anchor import save_arrays


class PhaseReferenceProvider:
    def __init__(self,bundle,journal):
        self.bundle,self.journal=bundle,journal
        self.folder=journal.folder/'phase_reference_raw';self.folder.mkdir(exist_ok=False)
        cfg=bundle['cfg'];element=bundle['setup']['spaces'][bundle['degree']].element.basix_element
        with journal.measured('cold_complete_phase_reference_15_grams'):
            self.factory=AffinePhaseReferenceTensor(element,kappa=bundle['kappa'],k0=cfg.k0,mu=cfg.mu_r,
                epsilon_by_tag={cfg.tags.air:cfg.eps_air,cfg.tags.substrate:cfg.eps_substrate,cfg.tags.grating:cfg.eps_grating},
                q=2*bundle['degree']+3)
        self.classes=[]

    def load(self,form,coordinates,*,tag,dimension):
        element=form.function_spaces[0].element.basix_element
        if element.hash()!=self.factory.element.hash() or dimension!=self.factory.element.dim:
            raise ValueError('phase provider live basis identity')
        with self.journal.measured('complete_phase_raw_class_combination'):
            tensor=self.factory.tensor(tag=tag,widths=axis_widths(coordinates))
        key=RawTensorCheckpoint.key(coordinates,tag)
        with self.journal.measured('phase_provider_atomic_save_reopen'):
            arrays=save_arrays(self.folder/(key+'.npz'),tensor=tensor,coordinates=coordinates,kappa=self.bundle['kappa'])
            with np.load(arrays['path'],allow_pickle=False) as f:
                if not np.array_equal(f['tensor'],tensor):raise ValueError('complete tensor bitwise reopen')
        identity=dict(key=key,tag=int(tag),dimension=int(dimension),degree=self.bundle['degree'],dtype=str(tensor.dtype),
            kappa=self.bundle['kappa'],element_hash=int(element.hash()),
            form_signature=form.module.ffi.string(form.ufcx_form.signature).decode('ascii'),
            producer_sha=self.journal.source_state['source_sha'],arrays=arrays,
            independent_reopen_bitwise=True,backend=self.factory.backend,raw_not_schur=True)
        self.classes.append(identity)
        return tensor,identity

    def record(self):
        return dict(backend=self.factory.backend,reference=self.factory.audit,classes=len(self.classes),
            cold_reference_required=True,ordinary_default_changed=False,orientation_MPC_applied_here=False)
