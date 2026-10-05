"""Parameterised storage stages. Scientific inputs are read only after guard."""
import argparse
import json
import os
import time
from pathlib import Path

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers.bound_array_identity import file_hash, read_arrays, read_json
from src.solvers.lossless_vector_bank import Backend, VectorBank, abi, consume, digest, layout, write_bank
from src.solvers.port_component_study import array_file, environment
from src.solvers.vector_storage_scope import ARTIFACT, ROOT, guard_source, plan_record, stage, window


def save(folder, name, **arrays):
    return array_file(folder/(name+'.npz'),compressed=True,**arrays)


def data(folder):
    plan=plan_record()
    original=read_json(plan['data'],ROOT)
    graph_record=read_json(plan['graph'],ROOT)
    graph=read_arrays(graph_record['graph'],ROOT,names=['keys','sizes','offsets'])
    blocks=layout(graph['keys'],graph['sizes'],graph['offsets'],13824)
    prepared={}
    for split in ('train','validation'):
        records=original['datasets'][split]
        vectors=[read_arrays(r['arrays'],ROOT,names=['canonical'])['canonical'] for r in records]
        if any(v.shape!=(42624,) for v in vectors):
            raise ValueError('complete finite canonical identity')
        prepared[split]=save(folder,split,canonical=np.asarray(vectors))
    return {'prepared':prepared,'blocks':blocks,'parents':{'data':plan['data'],'graph':plan['graph']},
            'trace_rows':13824,'internal_rows':28800,'heldout_consumed':False,
            'forbidden_parameters_read':[],'environment':environment(), 'abi':abi()}


def prepared(split):
    d=stage('DATA')
    values=read_arrays(d['prepared'][split],ROOT,names=['canonical'])['canonical']
    return values[:,:13824].copy(),d['blocks']


def encode_record(folder, name, vectors, blocks, method, weights=()):
    backend=Backend(plan_record()['backend'])
    receipt=write_bank(folder/(name+'.bank'),vectors,blocks,method,backend,weights)
    bank=VectorBank(receipt['path'],receipt['sha256'])
    receipt['object_bytes']=bank.object_bytes()
    receipt['producer_bit_roundtrip']=all(bank.get(i).tobytes()==v.tobytes() for i,v in enumerate(vectors))
    if not receipt['producer_bit_roundtrip']:
        raise ValueError('producer roundtrip failed')
    return receipt


def traditional(folder):
    vectors,blocks=prepared('train');validation,_=prepared('validation')
    vectors=np.concatenate([vectors,validation])
    results={}
    for method in plan_record()['traditional']:
        results[method]=encode_record(folder,method.replace(':','_'),vectors,blocks,method)
        write_json(folder/'traditional_checkpoint.json',results)
        print(json.dumps({'traditional':method,'bytes':results[method]['file_bytes']}),flush=True)
    best=min(results,key=lambda k:results[k]['object_bytes']['complete_trace_bank_object_bytes'])
    # Strict optimistic LOWER bound: zero remaining predictive payload, minimum
    # 1538 FP64 weights + one trace output/current + canonical row table. JSON
    # index/hash and block scratch only increase it; no entropy assertion.
    compulsory=1538*8+13824*16*2+13824*8
    target=.8*results[best]['object_bytes']['complete_trace_bank_object_bytes']
    gate={'best_traditional':best,'best_complete_object_bytes':results[best]['object_bytes']['complete_trace_bank_object_bytes'],
          'optimistic_unavoidable_lower_bound_bytes':compulsory,'target_80_percent_bytes':target,
          'training_admitted':compulsory<=target,'lower_bound_note':'zero payload/header allowed for optimistic feasibility; actual index/header/model accounted in results, no entropy guess'}
    return {'banks':results,'capacity_gate':gate,'status':'P2_TRAINING_ADMITTED' if gate['training_admitted'] else 'NO_COMPONENT_MEMORY_OPPORTUNITY'}


def train(folder, kind):
    if not stage('TRADITIONAL')['capacity_gate']['training_admitted']:
        return {'status':'NOT_RUN_CAPACITY_GATE','kind':kind}
    import torch
    from src.solvers.causal_storage_predictor import export, gradient_gate, model, positions
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    if torch.get_num_threads()!=1 or torch.get_num_interop_threads()!=1:
        raise ValueError('Torch effective threads')
    train_vectors,blocks=prepared('train');validation,_=prepared('validation')
    x,y=positions(train_vectors[:1],blocks)
    net=model(kind,plan_record()['training']['seed'])
    initial=np.concatenate([w.ravel() for w in export(net)])
    gate=gradient_gate(net,x,y,plan_record()['training']['seed']+1)
    write_json(folder/'gradient_gate.json',gate)
    if not gate['passed']:
        return {'status':'GRADIENT_NOT_QUALIFIED','kind':kind,'gradient_gate':gate}
    optimizer=torch.optim.Adam(net.parameters(),lr=1e-3)
    checkpoints=[];history=[]
    started=time.perf_counter()
    for update in range(257):
        if update in (0,64,128,256):
            weights=export(net)
            receipt=save(folder,f'{kind}_weights_{update}',**{f'w{i}':w for i,w in enumerate(weights)})
            bank=encode_record(folder,f'{kind}_validation_{update}',validation,blocks,kind,weights)
            checkpoints.append({'update':update,'weights':receipt,'validation_bank':bank})
            torch.save({'model':net.state_dict(),'optimizer':optimizer.state_dict(),'completed_updates':update},folder/f'{kind}_transaction_{update}.pt')
            write_json(folder/'training_checkpoint.json',{'kind':kind,'checkpoints':checkpoints,'history':history})
            print(json.dumps({'model':kind,'update':update,'validation_bytes':bank['file_bytes']}),flush=True)
        if update==256:
            break
        # One problem's causal positions resident at a time, fixed train16
        # cycle. All feature construction remains charged to training.
        x,y=positions(train_vectors[update%16:update%16+1],blocks)
        ids=(np.arange(4096)+(update//16)*4096)%len(x)
        xx,yy=torch.as_tensor(x[ids]),torch.as_tensor(y[ids])
        optimizer.zero_grad()
        loss=(net(xx)-yy).square().sum(dim=1).mean()
        if not torch.isfinite(loss):
            raise ValueError('nonfinite prediction training loss')
        loss.backward();optimizer.step()
        history.append({'update':update+1,'loss':float(loss.detach())})
    final=np.concatenate([w.ravel() for w in export(net)])
    if not np.isfinite(final).all() or np.array_equal(initial,final):
        raise ValueError('real training parameters did not change')
    chosen=min(checkpoints,key=lambda c:(c['validation_bank']['file_bytes'],c['update']))
    return {'status':'REAL_256_UPDATES_COMPLETED','kind':kind,'updates':256,'parameter_count':len(final),
            'parameter_change_norm':float(np.linalg.norm(final-initial)), 'gradient_gate':gate,
            'chosen':chosen,'checkpoints':checkpoints,'history':history,'elapsed_seconds':time.perf_counter()-started,
            'Torch_threads':[torch.get_num_threads(),torch.get_num_interop_threads()], 'DataLoader_workers':0,
            'selection':'whole actual validation stream including model/header/index; ties earlier', 'heldout_consumed':False}


def freeze(folder):
    traditional_result=stage('TRADITIONAL')
    models={}
    for kind in ('LIN','NN'):
        try:
            r=stage('TRAIN_'+kind)
        except FileNotFoundError:
            continue
        if r.get('status')=='REAL_256_UPDATES_COMPLETED':
            models[kind]=r['chosen']['weights']
    return {'frozen_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
            'models':models,'training_admitted':traditional_result['capacity_gate']['training_admitted'],
            'traditional':plan_record()['traditional'],'codec_abi':abi(),'plan_sha256':file_hash(__import__('src.solvers.vector_storage_scope',fromlist=['PLAN']).PLAN),
            'solver_queue_closed':True,'migration_allowed_after_this_record':True}


def pullback(g, vector):
    """Literal CSR conjugate-transpose accumulation; no SciPy/FE dependency."""
    shape=tuple(g['shape'])
    if vector.shape!=(shape[0],):
        raise ValueError('native migration vector shape')
    rows=np.repeat(np.arange(shape[0]),np.diff(g['bridge_indptr']))
    contributions=np.conjugate(g['bridge_data'])*vector[rows]
    result=np.zeros(shape[1],np.complex128)
    np.add.at(result,g['bridge_indices'],contributions)
    return result


def evaluation_data(folder):
    frozen=stage('FREEZE');p=plan_record();d=stage('DATA')
    datasets={};provenance={}
    if frozen['training_admitted'] and 'NN' in frozen['models'] and 'LIN' in frozen['models']:
        original=read_json(p['data'],ROOT)
        vectors=[read_arrays(r['arrays'],ROOT,names=['canonical'])['canonical'] for r in original['datasets']['heldout']]
        datasets['heldout']=save(folder,'heldout',canonical=np.asarray(vectors))
        provenance['heldout']={'original_receipts':[r['arrays'] for r in original['datasets']['heldout']], 'first_consumed_after_freeze':True}
    else:
        vectors,_=prepared('train');val,_=prepared('validation')
        fulls=[read_arrays(d['prepared'][s],ROOT,names=['canonical'])['canonical'] for s in ('train','validation')]
        datasets['train_validation']=save(folder,'train_validation',canonical=np.concatenate(fulls))
    # Mapping only, no old operator/CSR solve or native FE process.
    graph_record=read_json(p['graph'],ROOT)
    g=read_arrays(graph_record['graph'],ROOT,names=['bridge_data','bridge_indices','bridge_indptr','shape'])
    migration=read_arrays(p['migration'],ROOT,names=p['migration_members'])
    values=[]
    for name in p['migration_members']:
        v=migration[name]
        if v.ndim==2:
            values.extend(pullback(g,np.asarray(row)) for row in v)
        else:
            values.append(pullback(g,v))
    if len(values)!=16 or any(v.shape!=(42624,) for v in values):
        raise ValueError('fixed public migration inventory/bridge')
    datasets['migration']=save(folder,'migration',canonical=np.asarray(values))
    provenance['migration']={'input':p['migration'],'members':p['migration_members'],'mapping':'qualified J^H only, not A/AH', 'diagnostic_not_blind':True}
    return {'datasets':datasets,'blocks':d['blocks'],'provenance':provenance,'freeze':json.loads((ARTIFACT/'FREEZE.json').read_text()),'heldout_consumed':'heldout' in datasets}


def encode_evaluation(folder):
    d=stage('EVALUATION_DATA');frozen=stage('FREEZE');results={}
    models={k:list(read_arrays(r,ROOT).values()) for k,r in frozen['models'].items()}
    # w0..w5 lexical order is numeric for this frozen <=6 member schema.
    for family,receipt in d['datasets'].items():
        full=read_arrays(receipt,ROOT,names=['canonical'])['canonical']
        vectors=full[:,:13824].copy()
        results[family]={}
        for method in [*plan_record()['traditional'],*models]:
            results[family][method]=encode_record(folder,f'{family}_{method.replace(":","_")}',vectors,d['blocks'],method,models.get(method,()))
            print(json.dumps({'family':family,'encoded':method,'bytes':results[family][method]['file_bytes']}),flush=True)
            write_json(folder/'evaluation_encoding_checkpoint.json',results)
    return {'banks':results,'data':json.loads((ARTIFACT/'EVALUATION_DATA.json').read_text()),'frozen_models':frozen['models']}


def consumer(folder, family, method):
    receipt=stage('ENCODE_EVALUATION')['banks'][family][method]
    start=time.perf_counter();bank=VectorBank(receipt['path'],receipt['sha256']);loaded=time.perf_counter()-start
    scalars,current,seconds=consume(bank)
    arrays=save(folder,'consumer',scalars=scalars,current=current)
    # Deliberately contains no original vector/path or label read.
    return {'family':family,'method':method,'bank':receipt,'arrays':arrays,'load_seconds':loaded,'consumer_seconds':seconds,
            'object_bytes':bank.object_bytes(),'original_scientific_inputs_opened':[], 'traversals':2,'finite_operation':'vdot then fixed axpy','RAW_returns_view':method=='RAW'}


def analyze(folder):
    from src.solvers.lossless_vector_bank import causal_features, infer
    check=stage('CHECK');encoded=stage('ENCODE_EVALUATION');data_record=stage('EVALUATION_DATA');frozen=stage('FREEZE')
    models={k:list(read_arrays(r,ROOT).values()) for k,r in frozen['models'].items()}
    diagnostics=[];comparisons={}
    for family,receipt in data_record['datasets'].items():
        vectors=read_arrays(receipt,ROOT,names=['canonical'])['canonical'][:,:13824]
        banks=encoded['banks'][family]
        best=min(plan_record()['traditional'],key=lambda k:banks[k]['object_bytes']['complete_trace_bank_object_bytes'])
        comparisons[family]={'best_traditional':best,'complete_bytes':{k:v['object_bytes']['complete_trace_bank_object_bytes'] for k,v in banks.items()},
                             'files_bytes':{k:v['file_bytes'] for k,v in banks.items()},'NN_ratio':banks['NN']['object_bytes']['complete_trace_bank_object_bytes']/banks[best]['object_bytes']['complete_trace_bank_object_bytes'] if 'NN' in banks else None}
        for kind,weights in models.items():
            groups={}
            for block in data_record['blocks']:
                ids=np.asarray(block['rows']);p=ids.shape[1]
                for moment in range(1,p):
                    key=(block['kind'],block['axis'],moment)
                    group=groups.setdefault(key,{'count':0,'prediction_square_error':0.,'normalized_square_error':0.,'xor_bits':0,'leading_zero_bits':0,'sign_words_changed':0,'exponent_words_changed':0,'mantissa_words_changed':0})
                    for vector in vectors:
                        values=vector[ids];past=np.zeros((len(ids),4),complex);take=min(moment,4)
                        past[:,-take:]=values[:,moment-take:moment]
                        x,scale,raw=causal_features(past,block['kind'],block['axis'],moment,p)
                        predicted=infer(x,weights)*scale[:,None];predicted[raw]=0
                        original=np.ascontiguousarray(values[:,moment]).view('<u8').reshape(-1,2)
                        pw=np.ascontiguousarray(predicted).view('<u8').reshape(-1,2)
                        xor=original^pw
                        # Exact integer bit lengths; no log2(float(uint64)) roundoff.
                        lengths=np.zeros(xor.shape,np.uint8)
                        for bit in range(64):
                            lengths[(xor>>np.uint64(bit))!=0]=bit+1
                        truth=np.ascontiguousarray(values[:,moment]).view(np.float64).reshape(-1,2)
                        error=(truth-predicted)**2
                        group['count']+=len(ids);group['prediction_square_error']+=float(error.sum())
                        group['normalized_square_error']+=float((error/scale[:,None]**2).sum())
                        group['xor_bits']+=int(lengths.sum());group['leading_zero_bits']+=int((64-lengths).sum())
                        group['sign_words_changed']+=int(((xor>>np.uint64(63))!=0).sum())
                        group['exponent_words_changed']+=int((((xor>>np.uint64(52))&np.uint64(2047))!=0).sum())
                        group['mantissa_words_changed']+=int(((xor&np.uint64((1<<52)-1))!=0).sum())
            diagnostics.extend({'family':family,'model':kind,'entity_kind':key[0],'axis':key[1],'moment':key[2],**value} for key,value in groups.items())
    timing_gate=bool('heldout' in comparisons and all(v['NN_ratio'] is not None and v['NN_ratio']<=.8 for v in comparisons.values()))
    necessary={'target_trace_bytes':1684779264,'one_32_bank_bytes':53912936448,'conditional_two_32_banks_bytes':107825872896,
               'fraction_of_2e12_even_total_free_removal':107825872896/2e12,
               'peak_necessary':'V_best-V_NN-extra_workspace >=0.2*M_best; M_best<=5*(net_saving), and all training/preparation peaks compliant',
               'time_necessary':'C+H+r*d+other<=172800 and <=0.8*T_best for time NN20; r_max=(172800-C-H-other)/d when numerator nonnegative',
               'C':'unknown','target_read_count_r':'unknown','complete_engine_peak':'unknown','actual_target_bank_presence':'unknown',
               'cold_N_1_8_100':'H charged once then amortized H/N only conditional; no target C/r to turn into real qualification',
               'full_original_solver_lineage_known_lower_seconds':88656.94151362307,'historical_cold_FE_CSR_manual_IO':'unknown',
               'pipeline_integration':'research VectorBank callable get; not connected to a complete qualified engine',
               'training_peak_included_in_complete_cold_peak':True,'dot_bank_presence':'not proved by frozen published metadata, no dot code executed'}
    return {'status':'FROZEN_PREDICTIVE_STORAGE_CLOSED_NO_NN20' if not timing_gate else 'FINITE_COMPONENT_TIMING_GATE_OPEN',
            'comparisons':comparisons,'bit_diagnostics':diagnostics,'timing_three_repeats_admitted':timing_gate,
            'independent_checker':json.loads((ARTIFACT/'CHECK.json').read_text()),'qualification':check['status'],
            'necessary_conditions':necessary,'NN20':False,'PDE_pass':False,
            'interpretation':'MSE and XOR bit length differ: signs/exponents/mantissa and lossless postcoding measured separately, no universal entropy lower bound',
            'next_step':'only reconsider integration with a representative matched complete engine proving resident bank share/read count and NN advantage; no retraining of this frozen codec'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage');parser.add_argument('--family');parser.add_argument('--method')
    args=parser.parse_args();window.guard_worker_parent()
    folder=Path(os.environ['TASK042_V36_AUX_DIRECTORY']);identity=guard_source(folder)
    ARTIFACT.mkdir(parents=True,exist_ok=True)
    outputs=ARTIFACT/folder.name;outputs.mkdir(exist_ok=False)
    routines={'DATA':data,'TRADITIONAL':traditional,'FREEZE':freeze,'EVALUATION_DATA':evaluation_data,'ENCODE_EVALUATION':encode_evaluation,'ANALYSIS':analyze}
    start=time.perf_counter()
    if args.stage.startswith('TRAIN_'):
        result=train(outputs,args.stage.removeprefix('TRAIN_'))
    elif args.stage=='CONSUME':
        result=consumer(outputs,args.family,args.method)
    else:
        result=routines[args.stage](outputs)
    result.update(stage=args.stage,source=identity,environment=environment(),elapsed_seconds=time.perf_counter()-start,
                  A_AH_B=0,new_FE_JIT_LU_QR_Krylov_MPI=0,shared_workstation=True)
    write_json(outputs/'result.json',result)
    pointer={'path':str(outputs/'result.json'),'sha256':file_hash(outputs/'result.json')}
    name=f'CONSUME_{args.family}_{args.method.replace(":","_")}' if args.stage=='CONSUME' else args.stage
    if (ARTIFACT/(name+'.json')).exists():
        raise RuntimeError('immutable published phase; use diagnosed new attempt, retain old evidence')
    write_json(ARTIFACT/(name+'.json'),pointer)
    print(json.dumps({'stage':name,'result':pointer,'seconds':result['elapsed_seconds']}),flush=True)


if __name__=='__main__':
    main()
