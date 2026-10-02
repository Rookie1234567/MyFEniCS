"""AST-only production checker policy tests; no project or numerical imports."""
from pathlib import Path
import ast
import cmath
import copy
import json
import math
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT if (ROOT/'.git').exists() else ROOT.parents[2] / 'repo'


class PolicyImports(ast.NodeTransformer):
    """Keep stdlib policy execution while excluding every project/numeric import."""
    def visit_ImportFrom(self, node):
        if (node.module or '').startswith(('src.', 'benchmarks.')):
            return None
        return node

    def visit_Import(self, node):
        if any(item.name.startswith(('numpy', 'scipy', 'dolfinx', 'petsc4py')) for item in node.names):
            return None
        return node


def ast_module(name, path, injected=None):
    tree = ast.parse(path.read_text(), filename=str(path))
    tree = ast.fix_missing_locations(PolicyImports().visit(tree))
    value = ModuleType(name)
    sys.modules[name] = value
    value.__dict__.update({'__file__': str(path), **(injected or {})})
    exec(compile(tree, str(path), 'exec'), value.__dict__)
    return value


profile_module = ast_module('_Y_checker_profile_policy', REPO / 'src/solvers/y_orbit_direct_profile.py')
checker = ast_module('_Y_direct_saved_policy', ROOT / 'benchmarks/check_y_orbit_direct_probe.py',
    {'direct_profile_metadata': profile_module.direct_profile_metadata,
     'np': SimpleNamespace(exp=cmath.exp, pi=math.pi)})
generic = ast_module('_Y_quotient_saved_policy', ROOT / 'benchmarks/check_y_orbit_quotient_probe.py',
    {'reviewed_direct_profile_metadata': checker.reviewed_direct_profile_metadata,
     'bind_direct_checker_source': checker.bind_direct_checker_source})


def report(stage='solve', name='Y'):
    metadata = checker.reviewed_direct_profile_metadata(name)
    blocks = [{'q': q, 'shape': [n, n], 'nnz': 3, 'csr_prefix': f'q_{q}_S', 'CSR_sha256': 'a'*64}
        for q, n in enumerate(metadata.augmented_rows_per_q)]
    providers = []
    for b in range(metadata.replication_count):
        for p in range(2):
            for q in range(2):
                gp, gq = b+metadata.replication_count*p, b+metadata.replication_count*q
                providers.append({'twist': b, 'p': p, 'q': q, 'global_p': gp, 'global_q': gq,
                    'shape': [metadata.augmented_rows_per_q[gp], metadata.augmented_rows_per_q[gq]],
                    'nnz': 3 if p == q else 0, 'csr_prefix': f'direct_twist_{b}_block_{p}_{q}', 'CSR_sha256': 'a'*64})
    value = {'schema': checker.SCHEMA, 'direct_profile': name, 'profile': json.loads(json.dumps(metadata.identity())),
        'stage': stage, 'status': checker.PASSES[stage], 'degree': 4, 'physical_mode_count': 532,
        'source_clean_unchanged': True, 'official_results': False, 'prefactor_only': stage == 'prefactor',
        'PDE_solved': stage == 'solve', 'factor_count': 0 if stage == 'prefactor' else metadata.ny,
        'input_sha256': checker.INPUT_SHA, 'physical_generator_manifest_sha256': checker.PHYSICAL_MANIFEST,
        'shared_transforms': True, 'scope_flags': {'full_layout_entity_stream': True, 'fresh_global_and_local_carriers': True,
            'snapshots_reused': False, 'candidate_full_Ny_CSR_created': False, 'candidate_full_F_created': False,
            'candidate_full_Q_created': False, 'candidate_global_FE_square_matrix_created': False,
            'performance_or_target_capacity_claim': False}, 'reformed_blocks': blocks, 'direct_provider_blocks': providers,
        'original_operator_qualification': {'metadata_witness': 'original_complete'},
        'fresh_carrier_qualification': {'metadata_witness': 'fresh_complete'}}
    if stage == 'solve':
        value.update(factor={'input_blocks': copy.deepcopy(blocks), 'tests': [{'q': q} for q in range(metadata.ny)],
            'all_reformed_blocks_compared_before_factor': True, 'all_four_retained_simultaneously': name != 'Y',
            **({'all_six_retained_simultaneously': True, 'all_actual_q_retained_simultaneously': True,
                'factor_allowance_aggregate_bytes': metadata.factor_allowance_aggregate_bytes} if name == 'Y' else {})},
            regular_sources={name: {} for name in checker.SOURCES}, notched_sources={name: {} for name in checker.SOURCES},
            sampled_right_PC_defect={name: .001 for name in checker.SOURCES}, PC_defect_is_norm_bound=False,
            target_geometry_accuracy=False, no_2TB_or_48h_claim=True,
            changed_cells=[0, 1, 2] if name == 'Y' else [0, 1], sampled_notch_off_q_delta_relative=.01)
    shapes = checker.expected_array_shapes(value, stage)
    shapes.update({name: [2] for name in ('full_mpc_masters', 'full_mpc_coefficients', 'original_port_C_data',
        'original_port_C_indices', 'original_port_D_data', 'original_port_D_indices')})
    value['artifacts'] = {name: {'path': name+'.npy', 'file_sha256': 'f'*64, 'shape': shape, 'dtype': 'complex128',
        'payload_bytes': 16*math.prod(shape), 'finite_entries': math.prod(shape), 'nonfinite_entries': 0}
        for name, shape in shapes.items()}
    return value


def envelope(memory=3):
    required = memory*1024**3+checker.RESERVE_BYTES
    return {'launch_cap_bytes': required, 'effective_available_bytes': required+4*1024**3,
        'effective_total_bytes': 16*1024**3, 'reserve_bytes': 4*1024**3,
        'cgroup_limits': [{'limit_bytes': 16*1024**3, 'current_bytes': 1024**3}]}


def admission(memory=3):
    return {'requested_memory_gib': memory, 'requested_tree_cap_bytes': memory*1024**3,
        'required_cap_plus_evidence_reserve_bytes': memory*1024**3+checker.RESERVE_BYTES,
        'fresh_memory_envelope': envelope(memory), 'launch_admission_passed': True}


def bindings(stage='solve', name='Y'):
    value = report(stage, name)
    source = {'head': 'a'*40, 'branch': 'reviewed_branch', 'dirty': '',
        'files_sha256': {'benchmarks/check_y_orbit_direct_probe.py': 'b'*64}}
    environment = {'petsc_scalar_type': 'complex128', 'qualification_manifest_sha256': 'c'*64}
    value.update(source=source, environment=environment)
    metadata = checker.reviewed_direct_profile_metadata(name)
    provenance = {'source': source, 'environment': environment, 'schema': checker.SCHEMA, 'direct_profile': name,
        'stage': stage, 'degree': 4, 'input_sha256': checker.INPUT_SHA, 'command': ['run.py', '--direct-profile', name],
        'resource_contract': {'stage': stage, 'wall_seconds': 600, 'swap_bytes': 0, 'mpi': 1, 'math_threads': 1,
            'tree_cap_bytes': checker.TREE_CAP_BYTES, 'evidence_reserve_bytes': checker.RESERVE_BYTES,
            'factor_workspace_allowance_bytes': 0 if stage == 'prefactor' else metadata.factor_allowance_aggregate_bytes,
            'factor_fill_and_temporary_workspace_unknown': True, 'factor_L_U_statistics_copies_permitted': False,
            'performance_or_target_capacity_claim': False}}
    kwargs = {'checker_source': source, 'checker_environment': environment, 'stage': stage}
    if stage == 'solve':
        wall, memory = (1800, 2) if name == 'X' else (4500, 3)
        provenance['command'] += ['--research-wall-seconds', str(wall), '--research-memory-gib', str(memory)]
        provenance['resource_contract'].update(wall_seconds=wall, research_wall_seconds=wall,
            worker_phase_wall_seconds=wall-5.5, tree_cap_bytes=memory*1024**3, research_memory_gib=memory,
            requested_tree_cap_bytes=memory*1024**3, research_memory_launch_admission=admission(memory))
        kwargs.update(research_wall_seconds=wall, research_memory_gib=memory)
    return value, provenance, kwargs


def events(value, stage='solve'):
    metadata = checker.reviewed_direct_profile_metadata(value['direct_profile'])
    result = [{'event': name} for name in ('direct_fresh_carrier_qualification_complete',
        'direct_complete_original_operator_qualification', 'shared_complete_equivalence_before_any_factor')]
    result.append({'event': 'direct_complete_original_qualification_before_any_factor',
        'operator_receipt': value['original_operator_qualification'], 'fresh_carrier_receipt': value['fresh_carrier_qualification'],
        'input_blocks': value['reformed_blocks'], 'factor_count': 0})
    if stage == 'solve':
        for q in range(metadata.ny):
            payload = sum(value['artifacts'][f'q_{q}_S_{key}']['payload_bytes'] for key in ('data', 'indices', 'indptr'))
            allowance = (metadata.ny-q)*128*1024**2
            result.extend([{'event': 'allocation_admission', 'boundary': f'quotient_factor_q_{q}', 'admitted': True,
                'facts': {'retained_factor_count': q, 'LU_fill_and_workspace_unknown': True,
                    'factor_workspace_allowance_bytes': allowance}, 'remaining_factor_allowance_bytes': allowance,
                'current_tree_rss_bytes': 10**6, 'additional_payload_bytes': 3*payload, 'declared_workspace_bytes': 2*payload,
                'evidence_reserve_bytes': checker.RESERVE_BYTES,
                'projected_tree_bytes': 10**6+5*payload+allowance+checker.RESERVE_BYTES,
                'effective_tree_cap_bytes': 3*1024**3},
                {'event': 'all_branch_factor_created', 'q': q, 'factor_count': q+1, 'retained_factor_count': q+1,
                    'input_CSR_sha256': value['reformed_blocks'][q]['CSR_sha256']},
                {'event': 'all_branch_factor_retained', 'q': q, 'retained_factor_count': q+1,
                    'remaining_declared_allowance_bytes':(metadata.ny-q-1)*128*1024**2,'factor_memory_bytes':None}])
    return result


def modes():
    return [SimpleNamespace(side=side, m=m, n=n, polarization=polarization)
        for side in ('top', 'bottom') for m in range(-9, 10) for n in range(-3, 4) for polarization in ('s', 'p')]


def operator_proof():
    metadata = checker.reviewed_direct_profile_metadata('Y')
    sources = [{'cell_count': cells, 'independent_rows': rows, 'all_interior_rows': interiors,
        'full300_columns_per_cell': 300, 'complete_actual_coverage': True}
        for cells, rows, interiors in [(120, 23808, 12960), *[(40, 7936, 4320)]*3]]
    orbits = [{'grid_xz': [ix, iz], 'all_global_q_pairs': [{'p': p, 'q': q, 'cross_twist': p%3 != q%3}
        for p in range(6) for q in range(6)], 'local_twists': [{'b': b, 'all2x2_pairs': [
            {'p': p, 'q': q, 'global_p': b+3*p, 'global_q': b+3*q} for p in range(2) for q in range(2)]}
            for b in range(3)]} for ix in range(metadata.nx) for iz in range(metadata.nz)]
    return {'sources': sources, 'complete_actual_xz_y_orbits': orbits,
        'local_original_condensation': [{}, {}, {}], 'existing_provider_all2x2_full_columns': [{}, {}, {}]}


def shared_evidence(name='Y'):
    tree=ast.parse((REPO/'src/test/test_y_orbit_shared_storage_metadata.py').read_text())
    cls=next(item for item in tree.body if isinstance(item,ast.ClassDef) and item.name=='SharedStorageContracts')
    fixture=copy.deepcopy(next(item for item in cls.body if isinstance(item,ast.FunctionDef) and item.name=='evidence'))
    fixture.args.args=[]
    scope={};exec(compile(ast.Module(body=[fixture],type_ignores=[]),'<existing ownership policy fixture>','exec'),scope)
    evidence,descriptors=scope['evidence']()
    if name is None:return evidence,descriptors
    metadata=checker.reviewed_direct_profile_metadata(name)
    evidence.update(schema='task40extra.direct-shared-transform-equivalence.v1',direct_profile=name,same80_p4_only=False)
    if name=='Y':
        role=copy.deepcopy(evidence['roles'][-1]);role['role']='twist_2';evidence['roles'].append(role)
        extra=[copy.deepcopy(item) for item in evidence['owner_stages'] if item['stage'].startswith('twist_1')]
        for stage in extra:stage['stage']=stage['stage'].replace('twist_1','twist_2')
        index=next(i for i,item in enumerate(evidence['owner_stages']) if item['stage']=='all_sectors_retained_before_factor')
        evidence['owner_stages'][index:index]=extra
    for stage in evidence['owner_stages']:
        stage['stage']=stage['stage'].replace('_unshared_overlap','_streamed_controls_begin')
        stage['allocation_boundary']='shared_owner_receipt_'+stage['stage']
    for role in evidence['roles']:
        ny=metadata.ny if role['role']=='full' else 2
        records=[];offset=0;slot=0;definitions=[]
        for dimension,count,size in ((1,metadata.nx*(3*metadata.nz+2),4),
            (2,metadata.nx*(3*metadata.nz+1),24),(3,metadata.nx*metadata.nz,108)):
            for index in range(count):definitions.append((dimension,slot,size));slot+=size
        template=role['records'][0]
        for orbit in range(ny):
            for index,(dimension,first,size) in enumerate(definitions):
                item=copy.deepcopy(template);item.update(orbit=orbit,base=[dimension,index],dimension=dimension,
                    first=first,size=size,rows_offset=offset,rows_count=size,template_id=f'template-000{dimension}',
                    borrower_record_index=len(records)+1)
                records.append(item);offset+=size
        role.update(ny=ny,records=records,full_rows=metadata.storage_rows if role['role']=='full' else metadata.local_storage_rows,
            width=metadata.rows_per_q,independent_rows=ny*metadata.rows_per_q,record_count=len(records),base_count=len(definitions))
    return evidence,descriptors


class DirectYSavedCheckerMetadataTests(unittest.TestCase):
    def test_exact_Y_metadata_and_unmerged_float_widths(self):
        metadata = checker.reviewed_direct_profile_metadata('Y')
        self.assertEqual(metadata.dimensions, (4, 6, 5))
        self.assertEqual(metadata.q_port_counts, (76, 76, 76, 152, 76, 76))
        self.assertEqual(metadata.sector_port_counts, (228, 152, 152))
        self.assertEqual(metadata.augmented_rows_per_q, (1884, 1884, 1884, 1960, 1884, 1884))
        self.assertEqual(len(set(b-a for a,b in zip(metadata.global_axes[1],metadata.global_axes[1][1:]))), 4)
        self.assertTrue(checker.validate_profile(report()['profile']))
        for key, value in [('dimensions',[4,8,5]), ('q_port_counts',[76]*6), ('replication_count',2),
            ('local_storage_rows',13236), ('factor_allowance_aggregate_bytes',512*1024**2), ('physical_mode_count',531)]:
            bad = report()['profile']; bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): checker.validate_profile(bad)
        for name in (None, '', 'y', 'Ny6', 'Y6', 'same80', 'XY'):
            with self.subTest(name=name), self.assertRaises(ValueError): checker.reviewed_direct_profile_metadata(name)

    def test_all_six_shapes_three_twists_and_missing_alias_negatives(self):
        for stage in ('prefactor', 'solve'):
            value = report(stage)
            self.assertTrue(checker.validate_scope(value, stage))
            shapes = checker.validate_array_inventory(value, stage)
            self.assertEqual(shapes['independent_storage_rows'], [23808])
            self.assertEqual(shapes['actual_interior_positions'], [12960])
            self.assertEqual(shapes['full_mpc_slaves'], [1660])
            self.assertEqual(shapes['twist_2_independent_storage_rows'], [7936])
            self.assertEqual(shapes['twist_2_original_H'], [152])
            self.assertEqual(shapes['direct_twist_2_lower_rhs_local_state'], [7936])
            self.assertEqual(shapes['direct_twist_2_lower_rhs_global_state'], [23808])
            self.assertEqual(shapes['direct_twist_2_block_1_1_indptr'], [1885])
            if stage == 'solve':
                self.assertEqual(shapes['q_5_rhs_a'], [1884])
                self.assertEqual(shapes['aug_q_5_FE_rhs'], [23808])
                self.assertEqual(shapes['notch_physical_recovered_field'], [25468])
            for key in ('reformed_blocks','direct_provider_blocks'):
                bad = copy.deepcopy(value); bad[key].pop()
                with self.subTest(stage=stage,key=key), self.assertRaises(ValueError): checker.expected_array_shapes(bad,stage)
            bad=copy.deepcopy(value);bad['direct_provider_blocks'][-1]['global_q']=4
            with self.assertRaises(ValueError):checker.expected_array_shapes(bad,stage)
            bad=copy.deepcopy(value);bad['artifacts'].pop('twist_2_trace_original_rows')
            with self.assertRaises(ValueError):checker.validate_array_inventory(bad,stage)
        for key,value in [('all_six_retained_simultaneously',False),('all_actual_q_retained_simultaneously',False),
            ('all_four_retained_simultaneously',True),('factor_allowance_aggregate_bytes',512*1024**2)]:
            bad=report();bad['factor'][key]=value
            with self.assertRaises(ValueError):checker.expected_array_shapes(bad,'solve')
        for changed in ([0,1],[0,1,120],[0,1,1]):
            bad=report();bad['changed_cells']=changed
            with self.assertRaises(ValueError):checker.validate_scope(bad,'solve')

    def test_resource_tuple_and_complete_provenance(self):
        self.assertEqual(checker.direct_memory_cap('Y','solve',4500,3),3*1024**3)
        for args in [('Y','solve',4500,None),('Y','solve',1800,3),('Y','solve',4500,2),
            ('Y','prefactor',4500,3),('Y','solve',4500.,3),('Y','solve',4500,3.),('Y','solve',True,3)]:
            with self.subTest(args=args),self.assertRaises(ValueError):checker.direct_memory_cap(*args)
        self.assertTrue(checker.validate_direct_memory_launch(envelope(),direct_profile='Y',research_wall_seconds=4500,research_memory_gib=3))
        self.assertTrue(checker.validate_direct_memory_admission(admission(),direct_profile='Y',research_wall_seconds=4500))
        value,provenance,kwargs=bindings()
        self.assertTrue(checker.validate_metadata_bindings(value,provenance,value['artifacts'],**kwargs))
        for key,bad_value in [('factor_workspace_allowance_bytes',512*1024**2),('tree_cap_bytes',2*1024**3),
            ('factor_fill_and_temporary_workspace_unknown',False),('factor_L_U_statistics_copies_permitted',True)]:
            bad=copy.deepcopy(provenance);bad['resource_contract'][key]=bad_value
            with self.subTest(key=key),self.assertRaises(ValueError):checker.validate_metadata_bindings(value,bad,value['artifacts'],**kwargs)
        bad=envelope();bad['reserve_bytes']-=1
        with self.assertRaises(ValueError):checker.validate_direct_memory_launch(bad,direct_profile='Y',research_wall_seconds=4500,research_memory_gib=3)
        for name in ('X','XZ'):
            value,provenance,kwargs=bindings(name=name)
            self.assertTrue(checker.validate_metadata_bindings(value,provenance,value['artifacts'],**kwargs))
            self.assertTrue(checker.expected_array_shapes(value,'solve'))

    def test_six_factor_lifecycle_and_guarded_actual_CSR_bytes(self):
        value=report();stream=events(value)
        self.assertTrue(checker.validate_direct_event_contract(stream,value,'solve',research_wall_seconds=4500,research_memory_gib=3))
        self.assertEqual([item['remaining_factor_allowance_bytes']//1024**2 for item in stream if item['event']=='allocation_admission'],[768,640,512,384,256,128])
        for key,bad_value in [('remaining_factor_allowance_bytes',512*1024**2),('additional_payload_bytes',0),
            ('declared_workspace_bytes',0),('current_tree_rss_bytes',0),('evidence_reserve_bytes',0),
            ('projected_tree_bytes',0),('effective_tree_cap_bytes',4*1024**3)]:
            bad=copy.deepcopy(stream);bad[4][key]=bad_value
            with self.subTest(key=key),self.assertRaises(ValueError):checker.validate_direct_event_contract(bad,value,'solve',research_wall_seconds=4500,research_memory_gib=3)
        for mutation in ('missing','order','retain','hash','unknown_fill'):
            bad=copy.deepcopy(stream)
            if mutation=='missing':bad=bad[:-3]
            elif mutation=='order':bad[4],bad[5]=bad[5],bad[4]
            elif mutation=='retain':bad[6]['retained_factor_count']=0
            elif mutation=='hash':bad[5]['input_CSR_sha256']='b'*64
            else:bad[4]['facts']['LU_fill_and_workspace_unknown']=False
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):checker.validate_direct_event_contract(bad,value,'solve',research_wall_seconds=4500,research_memory_gib=3)
        value=report('prefactor',name='X');self.assertTrue(checker.validate_direct_event_contract(events(value,'prefactor'),value,'prefactor'))
        with self.assertRaises(ValueError):checker.validate_direct_event_contract(events(report('prefactor'),'prefactor'),report('prefactor'),'prefactor')

    def test_physical_original_alias_roles_and_all_three_transport_phases(self):
        physical=modes();sectors=checker.validate_direct_mode_roles(physical,'Y')
        self.assertEqual(tuple(map(len,sectors)),(228,152,152))
        self.assertEqual(sorted(i for sector in sectors for i in sector),list(range(532)))
        for b,sector in enumerate(sectors):
            self.assertEqual({int(physical[i].n)%6 for i in sector},{b,b+3})
            self.assertEqual({((int(physical[i].n)-b)//3)%2 for i in sector},{0,1})
        self.assertEqual({physical[i].n for i in sectors[0]},{-3,0,3})
        self.assertEqual(sum(mode.n%6==3 for mode in physical),152)
        for bad in (physical[:-1],physical[:-1]+[physical[0]]):
            with self.assertRaises(ValueError):checker.validate_direct_mode_roles(bad,'Y')
        cfg=SimpleNamespace(ky=.3+.0j,period_y=25*(7/135))
        source={'profile':{'name':'Y'},'entities':{'ny':6}}
        for b in range(3):
            eta=complex(*checker.receipt_transport_eta(source,cfg,b))
            self.assertLess(abs(eta-cmath.exp(1j*(.3*cfg.period_y+2*math.pi*b)/6)),1e-15)
            self.assertLess(abs((eta**2)**3-cmath.exp(1j*.3*cfg.period_y)),1e-12)
        for b in (3,-1,True):
            with self.assertRaises(ValueError):checker.receipt_transport_eta(source,cfg,b)

    def test_all20_orbits_36global_12local_24cross_twist_pairs(self):
        proof=operator_proof();self.assertTrue(checker.validate_direct_Y_operator_coverage(proof))
        for mutation in ('source','orbit','global_pair','cross_pair','twist','local_alias','condensation','provider'):
            bad=copy.deepcopy(proof)
            if mutation=='source':bad['sources'].pop()
            elif mutation=='orbit':bad['complete_actual_xz_y_orbits'].pop()
            elif mutation=='global_pair':bad['complete_actual_xz_y_orbits'][0]['all_global_q_pairs'].pop()
            elif mutation=='cross_pair':bad['complete_actual_xz_y_orbits'][0]['all_global_q_pairs'][1]['cross_twist']=False
            elif mutation=='twist':bad['complete_actual_xz_y_orbits'][0]['local_twists'].pop()
            elif mutation=='local_alias':bad['complete_actual_xz_y_orbits'][0]['local_twists'][2]['all2x2_pairs'][3]['global_q']=4
            elif mutation=='condensation':bad['local_original_condensation'].pop()
            else:bad['existing_provider_all2x2_full_columns'].pop()
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):checker.validate_direct_Y_operator_coverage(bad)

    def test_shared_full_three_twists_and_exact_owner_lifecycle(self):
        for name in (None,'X','XZ','Y'):
            evidence,descriptors=shared_evidence(name)
            self.assertTrue(generic.validate_shared_storage_metadata(evidence,descriptors,direct_profile=name))
        evidence,descriptors=shared_evidence()
        self.assertEqual([role['role'] for role in evidence['roles']],['full','twist_0','twist_1','twist_2'])
        self.assertEqual([role['record_count'] for role in evidence['roles']],[912,304,304,304])
        for mutation in ('role','records','ny','order','owner','cleanup','mutable_twist2'):
            bad=copy.deepcopy(evidence)
            if mutation=='role':bad['roles'].pop()
            elif mutation=='records':bad['roles'][3]['records'].pop()
            elif mutation=='ny':bad['roles'][0]['ny']=4
            elif mutation=='order':bad['roles'][2],bad['roles'][3]=bad['roles'][3],bad['roles'][2]
            elif mutation=='owner':bad['owner_stages']=[stage for stage in bad['owner_stages'] if stage['stage']!='twist_2_layout_after_build']
            elif mutation=='cleanup':bad['owner_stages'][-1]['cleanup_live_declared_owner_anchors']=1
            else:
                stage=next(item for item in bad['owner_stages'] if item['stage']=='all_sectors_retained_before_factor')
                view=copy.deepcopy(stage['views'][0]);view.update(name='twist_2.record.0.matrix',writeable=True)
                stage['views'].append(view);stage['sum_view_nbytes_with_aliases']+=view['view_nbytes']
                owner=next(item for item in stage['owners'] if item['owner_id']==view['owner_id']);owner['borrowers'].append(view['name'])
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):generic.validate_shared_storage_metadata(bad,descriptors,direct_profile='Y')

    def test_same_live_chain_requires_every_local_carrier(self):
        value=report();fresh={'global_carrier_identity_before':{'full':'same'},'global_carrier_identity_after':{'full':'same'},
            'local_carrier_identities':[{'twist':b} for b in range(3)]}
        value['fresh_carrier_qualification']=fresh
        expected={'global':fresh['global_carrier_identity_before'],'local':fresh['local_carrier_identities']}
        value.update(same_live_carrier_identity_before_factor=expected,same_live_carrier_identity_at_exit=expected)
        stream=[{'event':'direct_same_live_carrier_identity','boundary':'before_all_q_factors','unchanged':True,
            'actual':expected,'expected':expected}]+events(value)+[{'event':'direct_same_live_carrier_identity',
                'boundary':'before_successful_exit','unchanged':True,'actual':expected,'expected':expected}]
        self.assertTrue(checker.validate_same_live_carrier_chain(stream,value))
        bad=copy.deepcopy(value);bad['fresh_carrier_qualification']['local_carrier_identities'].pop()
        with self.assertRaises(ValueError):checker.validate_same_live_carrier_chain(stream,bad)
        bad=copy.deepcopy(stream);bad[-1]['actual']={'global':expected['global'],'local':expected['local'][:2]}
        with self.assertRaises(ValueError):checker.validate_same_live_carrier_chain(bad,value)

    def test_box_geometry_derives_three_Y_cells_and_preserves_X_XZ_two(self):
        # These dictionaries exercise the production support policy only. The
        # separately mandatory all300-column source verifier is a named stub.
        checker._check_source=lambda source,**kwargs:{'cell_count':kwargs['metadata'].cell_count}
        for name,x_cell,z_cell,y_cells,box in [('Y',2,2,(1,2,3),(25,33.5,25/6,100/6,40,80)),
            ('X',3,2,(1,2),(25,33.5,6.25,18.75,40,80)),('XZ',3,3,(1,2),(25,33.5,6.25,18.75,40,80))]:
            metadata=checker.reviewed_direct_profile_metadata(name);cells=[]
            for x in range(metadata.nx):
                for y in range(metadata.ny):
                    for z in range(metadata.nz):
                        grid=[x,y,z];widths=[metadata.global_axes[d][grid[d]+1]-metadata.global_axes[d][grid[d]] for d in range(3)]
                        cells.append({'cell_index':len(cells),'grid':grid,'widths':widths,'cell_info':0,'tag':2,
                            'native_dofs':{},'native_coordinates':{},'canonical_ids':{},'canonical_map':{},
                            'oriented_tensor':{'numeric_sha256':'a'*64},'raw_tensor':{},'complete_canonical_contribution':{}})
            regular={'cells':cells,'native':{},'entities':{},'interior_positions':{},'trace_positions':{}}
            notch=copy.deepcopy(regular);notch.update(role='notch',explicit_shared_entity_config_for_changed_material=True)
            changed=[]
            for cell in notch['cells']:
                if cell['grid'][0]==x_cell and cell['grid'][1] in y_cells and cell['grid'][2]==z_cell:
                    changed.append(cell['cell_index']);cell['tag']=1;cell['oriented_tensor']['numeric_sha256']='b'*64
            config={'tags':{'grating':2,'air':1}}
            value={'direct_profile':name,'notch_original_volume_source':notch,'changed_cells':changed,'physical_config':config,
                'notch_config':{**config,'air_void_box_nm':[number*(7/135) for number in box]}}
            checks=[];saved=SimpleNamespace(load=None,gate=None)
            checker.check_notch_source(value,saved=saved,regular=regular,add=lambda *args:checks.append(args))
            self.assertEqual(len(changed),3 if name=='Y' else 2);self.assertEqual(len(checks),1)
            for mutation in ('box','support','outside_tag','width'):
                bad=copy.deepcopy(value)
                if mutation=='box':bad['notch_config']['air_void_box_nm'][2]=6.25*(7/135)
                elif mutation=='support':bad['changed_cells'].pop()
                elif mutation=='outside_tag':bad['notch_original_volume_source']['cells'][0]['tag']=1
                else:bad['notch_original_volume_source']['cells'][0]['widths'][1]+=1e-16
                if mutation=='box' and name!='Y':continue
                with self.subTest(name=name,mutation=mutation),self.assertRaises(ValueError):checker.check_notch_source(bad,saved=saved,regular=regular,add=lambda *args:None)

    def test_exact_7full_13local_source_roles_and_Y_only_same_head(self):
        names=['dtn_boundary_phase_gauge.py','dtn_port_3d.py','fullspace_dtn_action.py',
            'fullspace_same_mesh_hcurl_pmg_physical.py','dtn_boundary_plane_qualification.py','modes_3d.py','config_3d.py',
            'y_orbit_quotient_context.py','fullspace_same_mesh_hcurl_pmg_global.py','y_orbit_condensed_adapter.py',
            'floquet_3d.py','floquet_3d_high_order.py','high_order_floquet_trace.py']
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);inventory={};digests={}
            for name in names:
                folder='common' if name in ('modes_3d.py','config_3d.py') else ('constraints' if name.startswith(('floquet_','high_order_floquet')) else 'solvers')
                relative=f'src/{folder}/{name}';path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(name)
                inventory[relative]=digests[name]=checker.file_sha(path)
            source={'head':'a'*40,'branch':'reviewed_branch','dirty':'','files_sha256':inventory}
            full={'source_sha256':{name:digests[name] for name in names[:7]}}
            self.assertEqual(len(checker.validate_context_source_role('full',full,source,source_root=root,direct_profile='Y')),7)
            for b,count in enumerate((228,152,152)):
                contract={'schema':'task40extra.y-orbit-two-cell-context.research.v1','twist_index':b,'direct_profile':'Y',
                    'physical_generator_manifest_sha256':checker.PHYSICAL_MANIFEST,'global_y_cells':6,'local_y_cells':2,
                    'global_q_indices':[b,b+3],'global_mode_count':532,'sector_mode_count':count,'replication_count':3}
                local={'source_sha256':digests,'y_orbit_quotient':{'contract':contract,'contract_sha256':checker.digest_json(contract),
                    'actual_local_cells':40,'actual_local_storage_rows':8940,'twist_requires_global_dual_rhs_transport':True}}
                self.assertEqual(len(checker.validate_context_source_role(f'twist_{b}',local,source,source_root=root,direct_profile='Y')),13)
                for key,bad_value in [('global_q_indices',[b,b+2]),('global_y_cells',4),('replication_count',2),('sector_mode_count',304)]:
                    bad=copy.deepcopy(local);bad['y_orbit_quotient']['contract'][key]=bad_value
                    bad['y_orbit_quotient']['contract_sha256']=checker.digest_json(bad['y_orbit_quotient']['contract'])
                    with self.subTest(b=b,key=key),self.assertRaises(ValueError):checker.validate_context_source_role(f'twist_{b}',bad,source,source_root=root,direct_profile='Y')
                bad=copy.deepcopy(local);bad['source_sha256'].pop(names[-1])
                with self.assertRaises(ValueError):checker.validate_context_source_role(f'twist_{b}',bad,source,source_root=root,direct_profile='Y')
            with self.assertRaises(ValueError):checker.validate_context_source_role('twist_3',full,source,source_root=root,direct_profile='Y')
            self.assertTrue(checker.bind_direct_checker_source(source,copy.deepcopy(source),direct_profile='Y')['same_head_exact_source_identity'])
            changed=copy.deepcopy(source);changed['head']='b'*40
            with self.assertRaises(ValueError):checker.bind_direct_checker_source(source,changed,direct_profile='Y')
            self.assertTrue(generic.admit_checker_output(source,source,worker_directory=root/'worker',output_directory=root/'out',
                explicit_checker_directory=True,prior_checker_output=False,direct_profile='Y'))

    def test_arithmetic_residual_and_mask_contracts_remain_exact_source(self):
        original=ast.parse((REPO/'benchmarks/check_y_orbit_direct_probe.py').read_text())
        staged=ast.parse((ROOT/'benchmarks/check_y_orbit_direct_probe.py').read_text())
        for name in ('residual_representation_binding','validate_gauss','validate_descriptor_payload','load_direct_events'):
            old=next(item for item in original.body if isinstance(item,ast.FunctionDef) and item.name==name)
            new=next(item for item in staged.body if isinstance(item,ast.FunctionDef) and item.name==name)
            self.assertEqual(ast.dump(old,include_attributes=False),ast.dump(new,include_attributes=False))
        old=next(item for item in original.body if isinstance(item,ast.FunctionDef) and item.name=='check_raw_carriers')
        new=next(item for item in staged.body if isinstance(item,ast.FunctionDef) and item.name=='check_raw_carriers')
        old_mask=next(item for item in old.body if isinstance(item,ast.FunctionDef) and item.name=='masks')
        new_mask=next(item for item in new.body if isinstance(item,ast.FunctionDef) and item.name=='masks')
        self.assertEqual(ast.dump(old_mask,include_attributes=False),ast.dump(new_mask,include_attributes=False))
        def residual_tail(tree):
            function=next(item for item in tree.body if isinstance(item,ast.FunctionDef) and item.name=='check_solve')
            loop=next(item for item in function.body if isinstance(item,ast.For) and isinstance(item.target,ast.Tuple)
                and [getattr(target,'id','') for target in item.target.elts]==['label','family','source_name','packet'])
            index=next(i for i,item in enumerate(loop.body) if isinstance(item,ast.Assign)
                and any(isinstance(target,ast.Name) and target.id=='volume_source' for target in item.targets))
            return ast.dump(ast.Module(body=loop.body[index:],type_ignores=[]),include_attributes=False)
        self.assertEqual(residual_tail(original),residual_tail(staged))
        old_quotient=ast.parse((REPO/'benchmarks/check_y_orbit_quotient_probe.py').read_text())
        new_quotient=ast.parse((ROOT/'benchmarks/check_y_orbit_quotient_probe.py').read_text())
        protected=('validate_scope','bind_checker_source','csr_row_sort_permutation','validate_pinned_full_q_asset',
            'sort_pinned_historical_full_q','validate_metadata_bindings','validate_recovery_identity_bindings',
            'validate_factor_event_contract','validate_historical_file_metadata','validate_restoration_metadata',
            'expected_array_shapes','validate_array_inventory','per_mode_operation_error','validate_shared_record_key')
        for name in protected:
            old=next(item for item in old_quotient.body if isinstance(item,ast.FunctionDef) and item.name==name)
            new=next(item for item in new_quotient.body if isinstance(item,ast.FunctionDef) and item.name==name)
            self.assertEqual(ast.dump(old,include_attributes=False),ast.dump(new,include_attributes=False),name)
        for name in ('DIRECT_EVENT_WORKER_HEAD','DIRECT_EVENT_WORKER_SOURCE_SHA','DIRECT_EVENT_WORKER_CHECKERS','DIRECT_EVENT_ALLOWED_PATHS'):
            def assignment(tree):
                return next(item for item in tree.body if isinstance(item,ast.Assign)
                    and any(isinstance(target,ast.Name) and target.id==name for target in item.targets))
            self.assertEqual(ast.dump(assignment(original),include_attributes=False),ast.dump(assignment(staged),include_attributes=False),name)


if __name__=='__main__':
    unittest.main()
