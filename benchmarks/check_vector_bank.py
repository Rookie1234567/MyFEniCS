"""Independent original-byte and literal consumer checker, not a solver."""
import json
import os
from pathlib import Path

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers.bound_array_identity import file_hash, read_arrays, read_json
from src.solvers.lossless_vector_bank import VectorBank
from src.solvers.vector_storage_scope import ARTIFACT, ROOT, guard_source, plan_record, stage, window


def reference_consumer(vectors):
    current=np.zeros(vectors.shape[1],np.complex128);scalars=[]
    for order in (list(range(len(vectors))),list(reversed(range(len(vectors))))):
        for i in order:
            scalars.append(np.vdot(vectors[i],current))
            for lo in range(0,len(current),256):
                current[lo:lo+256]+=complex((i+1)/32,(i%3-1)/64)*vectors[i,lo:lo+256]
    return np.asarray(scalars),current


def literal_check(bank, originals):
    if originals.shape!=(bank.header['vectors'],bank.header['ntrace']):
        raise ValueError('fixed complete bank inventory')
    for i,v in enumerate(originals):
        if bank.get(i).tobytes()!=v.tobytes():
            raise ValueError('original canonical bits differ: '+str(i))
    return True


def original_full(family, data_record):
    """Original evidence, not the encoder's prepared-vector cache."""
    p=plan_record()
    if family=='heldout':
        return np.asarray([read_arrays(r,ROOT,names=['canonical'])['canonical'] for r in data_record['provenance']['heldout']['original_receipts']])
    if family=='migration':
        g=read_arrays(read_json(p['graph'],ROOT)['graph'],ROOT,names=['bridge_data','bridge_indices','bridge_indptr','shape'])
        source=read_arrays(p['migration'],ROOT,names=p['migration_members'])
        result=[]
        # Independent explicit row traversal, not producer pullback/cache.
        for name in p['migration_members']:
            for v in source[name]:
                out=np.zeros(int(g['shape'][1]),np.complex128)
                for row in range(int(g['shape'][0])):
                    lo,hi=g['bridge_indptr'][row:row+2]
                    for i in range(int(lo),int(hi)):
                        out[g['bridge_indices'][i]]+=np.conjugate(g['bridge_data'][i])*v[row]
                result.append(out)
        return np.asarray(result)
    original=read_json(p['data'],ROOT)
    return np.asarray([read_arrays(r['arrays'],ROOT,names=['canonical'])['canonical'] for s in ('train','validation') for r in original['datasets'][s]])


def main():
    window.guard_worker_parent()
    folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);source=guard_source(folder)
    d=stage('EVALUATION_DATA');encoded=stage('ENCODE_EVALUATION');rows=[]
    for family,receipt in d['datasets'].items():
        full=read_arrays(receipt,ROOT,names=['canonical'])['canonical']
        independent=original_full(family,d)
        if full.tobytes()!=independent.tobytes():
            raise ValueError('prepared vectors differ from original independent evidence')
        originals=full[:,:13824].copy()
        expected_scalars,expected_current=reference_consumer(originals)
        for method,bank_receipt in encoded['banks'][family].items():
            bank=VectorBank(bank_receipt['path'],bank_receipt['sha256'])
            literal_check(bank,originals)
            record=stage(f'CONSUME_{family}_{method.replace(":","_")}')
            outputs=read_arrays(record['arrays'],ROOT)
            if outputs['scalars'].tobytes()!=expected_scalars.tobytes() or outputs['current'].tobytes()!=expected_current.tobytes():
                raise ValueError('literal vdot/axpy all-bit output identity')
            complete=True
            for i in range(len(full)):
                reconstructed=np.concatenate([bank.get(i),full[i,13824:]])
                complete &= reconstructed.tobytes()==full[i].tobytes()
            if not complete:
                raise ValueError('all full independent coefficients/internal bits')
            rows.append({'family':family,'method':method,'vectors':len(full),'trace_complex_values':int(originals.size),
                         'trace_all_bits':True,'full_canonical_all_bits':True,'all_consumer_outputs_all_bits':True,
                         'bank_sha256':bank_receipt['sha256'],'consumer_arrays_sha256':record['arrays']['sha256'],
                         'file_bytes':bank_receipt['file_bytes'],'object_bytes':bank.object_bytes(),
                         'full_vector_scenario_add_internal_bytes':int(full[:,13824:].nbytes)})
    result={'status':'FINITE_LOSSLESS_STORAGE_COMPONENT_ONLY','checks':rows,'source':source,
            'no_original_inputs_in_decoder':True,'originals_only_in_independent_checker':True,
            'A_AH_B':0,'PDE_qualification':False,'NN20_qualification':False}
    write_json(folder/'independent_check.json',result)
    write_json(ARTIFACT/'CHECK.json',{'path':str(folder/'independent_check.json'),'sha256':file_hash(folder/'independent_check.json')})
    print(json.dumps({'status':result['status'],'route_family_checks':len(rows)}),flush=True)


if __name__=='__main__':
    main()
