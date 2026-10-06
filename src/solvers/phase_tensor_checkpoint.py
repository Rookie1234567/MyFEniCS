"""Write full, exact raw Ckappa class tensors without caching solver handles."""
import hashlib
from pathlib import Path
import numpy as np
from src.runners.task042_shared import write_json
from .scattering_anchor import save_arrays


class RawTensorCheckpoint:
    def __init__(self,folder,bundle,journal,*,reader=None):
        self.folder=Path(folder);self.folder.mkdir(exist_ok=False)
        self.bundle=bundle;self.journal=journal;self.classes=[];self.failures=[];self.bykey={};self.reader=reader

    @staticmethod
    def key(coordinates,tag):
        return hashlib.sha256(np.asarray(coordinates,np.float64).tobytes()+str(int(tag)).encode()).hexdigest()

    def __call__(self,form,kernels,coordinates,*,tag,dimension):
        from .hcurl_assembly_time_condensation import _tabulate_raw_tensor_class
        key=self.key(coordinates,tag)
        if self.reader is not None:
            hit=self.reader.load(form,coordinates,tag=tag,dimension=dimension)
            if hit is not None:
                tensor,identity=hit
                self.classes.append(identity);self.bykey[key]=len(self.classes)-1
                write_json(self.folder/'manifest.json',self.record())
                return tensor
        with self.journal.measured('raw_exact_tensor_class_'+str(len(self.classes)+len(self.failures))):
            tensor=_tabulate_raw_tensor_class(form,kernels,coordinates,tag=tag,dimension=dimension)
        try:
            with self.journal.measured('raw_tensor_atomic_save_and_reopen'):
                receipt=save_arrays(self.folder/(key+'.npz'),tensor=tensor,coordinates=coordinates,kappa=self.bundle['kappa'])
                with np.load(receipt['path'],allow_pickle=False) as reopened:
                    if not np.array_equal(reopened['tensor'],tensor):raise ValueError('persisted full raw tensor differs')
                identity=dict(key=key,tag=int(tag),dimension=int(dimension),degree=self.bundle['degree'],dtype=str(tensor.dtype),
                    kappa=self.bundle['kappa'],element_hash=int(form.function_spaces[0].element.basix_element.hash()),
                    form_signature=form.module.ffi.string(form.ufcx_form.signature).decode('ascii'),
                    producer_sha=self.journal.source_state['source_sha'],arrays=receipt,independent_reopen_bitwise=True)
                self.classes.append(identity);self.bykey[key]=len(self.classes)-1
                write_json(self.folder/'manifest.json',self.record())
        except (OSError,ValueError) as error:
            # A storage failure must preserve the correctly returned in-memory
            # tensor and cannot force another expensive kernel evaluation.
            self.failures.append(dict(key=key,error=repr(error)))
            self.journal.event('raw_tensor_persistence_failed_in_memory_retained',key=key,error=repr(error))
        return tensor

    def finish(self,setup,degree):
        from .hcurl_assembly_time_condensation import _canonical_axis_aligned_coordinates
        mesh=setup['mesh'];tags=setup['mesh_data'].cell_tags.values
        keys=[];jac=[]
        for c,tag in enumerate(tags):
            coordinates,_=_canonical_axis_aligned_coordinates(mesh,c,tolerance=1e-11,geometry_identity_policy='raw_unrounded')
            keys.append(self.key(coordinates,tag))
            # Exact affine J from the actual canonical hexahedron; this is
            # metadata, never a rounded tensor equivalence class.
            import basix
            ref=basix.cell.geometry(basix.CellType.hexahedron)
            fit=np.column_stack((ref,np.ones(8)))
            jac.append(np.linalg.lstsq(fit,coordinates.reshape(8,3),rcond=None)[0][:3].T)
        self.layout=save_arrays(self.folder/'cell_layout.npz',cell_class_key_utf8=np.asarray(keys,dtype='S64'),
            cell_class_index=np.asarray([self.bykey.get(k,-1) for k in keys],np.int32),J=np.asarray(jac),
            material_tag=tags,permutations=mesh.topology.get_cell_permutation_info(),
            native_cell_dofs=np.asarray([setup['spaces'][degree].dofmap.cell_dofs(c) for c in range(len(tags))]))
        write_json(self.folder/'manifest.json',self.record())

    def record(self):
        return dict(producer=self.journal.source_state,classes=self.classes,persistence_failures=self.failures,cell_layout=getattr(self,'layout',None),
            payload='full original raw Ckappa tensor; not Schur, matrix or factor',
            stored_bytes=sum(Path(x['arrays']['path']).stat().st_size for x in self.classes if not x.get('reused_parent')),
            readonly_reuse=None if self.reader is None else self.reader.record(),
            manifest_sha256_dependencies='per-class full producer hashes, actual basis/form, kappa, dtype and coordinates')
