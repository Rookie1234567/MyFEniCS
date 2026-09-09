"""Formal recursive-PC orchestration and scalar evidence; numerical core is shared."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path


def audit_costs(bundle):
    ledger = bundle['inexact_ledger']
    return dict(audits=ledger.audit_count, extra_A6=ledger.A_count, extra_PH=ledger.PH_count,
        extra_A6_seconds=ledger.A_seconds, extra_PH_seconds=ledger.PH_seconds,
        audit_seconds=ledger.audit_seconds, action_counts='attempted; includes failed audit')


def recursive_snapshot(bundle):
    return dict(storage=bundle['numerical_storage'], counts=dict(bundle['counts']),
        p2_counts=dict(bundle['p2_inverse'].counts), bottom=dict(bundle['p2_inverse'].bottom.audit),
        p2_matrix=dict(bundle['p2_matrix_facts']), H4=bundle['h4_setup']['light_facts'],
        inexact_audit=audit_costs(bundle))


def build_formal_recursive(cfg, comm, contract, *, sample, ledger, directory, identity):
    from dolfinx.jit import get_options
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from src.solvers.physical_recursive_coarse import build_recursive_physical_solver
    from .physical_diagnosis_worker import save_packet
    cache = (directory/'jit_cache').resolve()
    if (os.environ.get('XDG_CACHE_HOME') != str(cache) or
            Path(get_options(SAME_MESH_JIT_OPTIONS)['cache_dir']).resolve() != cache/'fenics'):
        raise RuntimeError('recursive formal cache was not isolated before worker imports')
    slowest = -1.
    def save(name, facts):
        save_packet(directory, name, dict(identity=identity, **facts))
    def observe(rhs, result):
        nonlocal slowest
        facts=result['facts']
        ledger.append('recursive_inner.jsonl', dict(identity=identity, **facts))
        if facts['seconds'] > slowest:
            save('recursive_slowest_I4', dict(rhs=rhs.array.copy(), solution=result['solution'].array.copy(),
                applied=result['applied'].array.copy(), residual=result['residual'].array.copy(), facts=facts))
            slowest=facts['seconds']
    bundle=build_recursive_physical_solver(cfg, comm, target=contract['intermediate']['relative_tolerance'],
        sample=sample, marker=ledger.marker, save=save, observe_inner=observe,
        stop_requested=lambda: ledger.stop_signal is not None)
    identity['mode_sha256']=bundle['fine']['mode_sha256']
    pc=bundle['pc']
    def apply(source):
        before=dict(bundle['counts']); p2_before=dict(bundle['p2_inverse'].counts)
        audit_before=audit_costs(bundle)
        value=None
        try:
            value=pc.apply(source)
            audit_after=audit_costs(bundle)
            row=dict(deepcopy(pc.last_apply_facts), identity=dict(identity),
                input_sha256=hashlib.sha256(source.array.tobytes()).hexdigest(),
                recursive_counts={k:v-before.get(k,0) for k,v in bundle['counts'].items()},
                p2_counts={k:v-p2_before.get(k,0) for k,v in bundle['p2_inverse'].counts.items()},
                audit_costs={k:v-audit_before[k] for k,v in audit_after.items() if k!='action_counts'})
            ledger.append('pc_applies.jsonl',row)
            return value
        except BaseException as exc:
            if value is not None:value.destroy()
            save(f'recursive_PC_{pc.attempted:06d}_failure',dict(input=source.array.copy(),
                stages=pc.last_apply_facts,counts=dict(bundle['counts']),audit_costs=audit_costs(bundle),
                reason=str(exc)))
            raise
    return bundle,apply


def audit_recursive_exit(bundle, ledger):
    # Owned last q/z/eps packet; no call to I4 and no reconstruction of a past inverse.
    before=audit_costs(bundle)
    result=bundle['inexact_ledger'].audit_last()
    after=audit_costs(bundle)
    ledger.append('recursive_exit_audit.jsonl',dict(audit=result,
        last_PC=bundle['pc'].apply_count,
        costs={k:v-before[k] for k,v in after.items() if k!='action_counts'},total=after))
    return recursive_snapshot(bundle)


def compare_native_rhs(current_map, reference_map, current_rhs, reference_rhs):
    import numpy as np
    if current_map.keys()!=reference_map.keys() or any(not np.array_equal(v,reference_map[k]) for k,v in current_map.items()):
        raise ValueError('recursive native-map field differs from frozen original')
    if current_rhs.shape!=reference_rhs.shape:
        raise ValueError('recursive original RHS shape differs')
    difference=float(np.linalg.norm(current_rhs-reference_rhs)/max(np.linalg.norm(reference_rhs),np.finfo(float).tiny))
    if not np.isfinite(difference) or difference>1e-10:
        raise ValueError('recursive original RHS differs')
    return dict(native_map='exact_fieldwise',rhs_relative_difference=difference,rhs_limit=1e-10)


def verify_frozen_recursive_identity(bundle, rhs, payload):
    """Read only the frozen map and b; no reference solution is loaded before solve."""
    import json
    import numpy as np
    from .actual_error_diagnosis import checked_json
    from .physical_diagnostic_completion import load_packet
    from src.solvers.condensed_fine_reference import native_map_arrays
    binding=json.loads(Path('input/task39extra/actual_error_evidence.json').read_text())
    audit=checked_json(binding['reference_audit'],binding['reference_audit_sha256'])
    hashes={x['path']:x['sha256'] for x in audit['artifact_hashes']}
    root=Path(binding['reference_root']);record_path=root/'reference_full_residual.json'
    record=checked_json(record_path,hashes[str(record_path)])
    if (record['identity']['original_physical_sha256']!=payload['provenance']['physical_model_sha256'] or
            record['identity']['mode_sha256']!=bundle['fine']['mode_sha256']):
        raise ValueError('recursive frozen physical/mode identity differs')
    map_path=root/'reference_native_map.json';checked_json(map_path,hashes[str(map_path)])
    reference_map=load_packet(map_path)
    # Packet metadata is not part of the map's fieldwise identity.
    current=native_map_arrays(bundle['levels']['spaces'][6],bundle['levels']['floquets'][6])
    archive=Path(record['arrays']['path'])
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=record['arrays']['sha256']:
        raise ValueError('frozen RHS archive hash differs')
    with np.load(archive,allow_pickle=False) as arrays:
        result=compare_native_rhs(current,{k:reference_map[k] for k in current},rhs.array,arrays[record['b']['array_key']])
    result.update(reference_record_sha256=hashes[str(record_path)],native_map_record_sha256=hashes[str(map_path)],
        reference_rhs_archive_sha256=record['arrays']['sha256'],reference_solution_read=False)
    return result
