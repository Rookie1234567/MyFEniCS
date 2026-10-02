"""Stdlib/AST storage-source and nonvacuity contracts; no project numerics."""
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
CHECKER=ROOT/'benchmarks/check_y_orbit_quotient_probe.py'
RUNNER=ROOT/'benchmarks/run_y_orbit_quotient_probe.py'
BRIDGE=ROOT/'benchmarks/y_orbit_shared_storage_bridge.py'


def extracted(path,names):
    tree=ast.parse(path.read_text())
    body=[node for node in tree.body if isinstance(node,ast.Assign) or isinstance(node,ast.FunctionDef) and node.name in names]
    scope={'__file__':str(path),'Path':Path,'json':json,'hashlib':hashlib,'math':math,'re':re}
    exec(compile(ast.Module(body=body,type_ignores=[]),str(path),'exec'),scope)
    return scope


class SharedStorageContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge=extracted(BRIDGE,{'digest_json','validate_storage_source_bridge','validate_loaded_storage_bridge'})
        cls.checker=extracted(CHECKER,{'finite_gate','validate_shared_storage_metadata','validate_shared_record_key'})
        cls.runner=extracted(RUNNER,{'plan_metadata'})

    def sources(self):
        # A bounded synthetic inventory tests policy, not historical qualification.
        old={path:'a'*64 for path in self.bridge['ALLOWED_PATHS'] if not path.endswith('_bank.py')}
        old['src/solvers/unchanged_physical.py']='b'*64
        new={**old,**{path:'c'*64 for path in self.bridge['ALLOWED_PATHS']}}
        self.bridge['WORKER_SOURCE_MANIFEST_SHA256']=self.bridge['digest_json'](old)
        worker={'head':self.bridge['WORKER_HEAD'],'branch':'task40extra_dot_parallel_cloud','dirty':'','files_sha256':old}
        candidate={'head':'d'*40,'branch':worker['branch'],'dirty':'','files_sha256':new}
        env={name:'same' for name in self.bridge['ENVIRONMENT_FIELDS']}
        return worker,candidate,env

    def evidence(self):
        desc={};roles=[]
        for name,ny in (('full',4),('twist_0',2),('twist_1',2)):
            records=[];offset=0
            slot=0;definitions=[]
            for dimension,count,size in ((1,68,4),(2,64,24),(3,20,108)):
                for index in range(count):definitions.append((dimension,slot,size));slot+=size
            for orbit in range(ny):
                for index,(dimension,first,size) in enumerate(definitions):
                    records.append({'orbit':orbit,'base':[dimension,index],'dimension':dimension,'first':first,'size':size,
                        'rows_offset':offset,'rows_count':size,'template_id':f'template-000{dimension}',
                        'borrower_record_index':len(records)+1,'actual_key':{'dimension':dimension},
                        'matrix_sha256':'e'*64,'inverse_sha256':'e'*64,'rows_owner_id':'rows','matrix_owner_id':'matrix',
                        'inverse_owner_id':'inverse','matrix_difference':0.,'inverse_difference':0.,'inverse_composition':0.,
                        'nonhermitian_pairing':0.})
                    offset+=size
            directions=[{'direction':direction,'relative_difference':0.,'complete_columns':108,'panel_columns_max':32,
                'input_sha256':'e'*64,'default_action_sha256':'e'*64,'shared_action_sha256':'e'*64} for direction in
                ('primal_to_canonical','primal_from_canonical','dual_to_canonical','dual_from_canonical','functional_to_canonical','functional_from_canonical')]
            roles.append({'role':name,'full_rows':17204 if ny==4 else 8940,'ny':ny,'width':3968,'independent_rows':ny*3968,
                'record_count':len(records),'base_count':152,'records':records,'references':{f'template-000{i}':{} for i in (1,2,3)},
                'record_rows_artifact':'rows_'+name,'directions':directions,
                'complete_native_independent_partition_equal':True,'complete_orbit_base_slot_partition_equal':True,
                'every_actual_record_matrix_inverse_compared':True,'all_six_complete_operator_columns_compared':True,
                'shared_bank_instance_equal':True,'mutable_transform_borrow_detected':False,'key_collision_detected':False})
        names=['before_collect']
        for role in ('full','twist_0','twist_1'):
            names.extend([role+'_after_collect',role+'_unshared_overlap',role+'_after_first_inverse_request',
                role+'_after_first_inverse_direction',role+'_after_all_six_directions'])
            if role!='full':names.append(role+'_layout_after_build')
        names.extend(['all_sectors_retained_before_factor','apply_recovery_complete','cleanup'])
        stages=[];all_refs={}
        for stage in names:
            inverse_count=(0 if stage in ('before_collect','full_after_collect','full_unshared_overlap') else
                           1 if stage=='full_after_first_inverse_request' else 3)
            templates=[];views=[];owners=[];refs={}
            if stage not in ('before_collect','cleanup'):
                for dimension,size in ((1,4),(2,24),(3,108)):
                    token=f'template-000{dimension}';templates.append({'template_id':token,'keys':[{'dimension':dimension}],
                        'matrix_sha256':'e'*64,'inverse_sha256':'e'*64 if dimension<=inverse_count else None})
                    for member in ('matrix','inverse'):
                        if member=='inverse' and dimension>inverse_count:continue
                        owner_id=token+'_'+member;name=f'bank.template.000{dimension}.{member}';count=size*size*16
                        owner={'owner_id':owner_id,'owner_type':'builtins.bytes','allocation_nbytes':count,'sha256':'e'*64,'borrowers':[name]}
                        view={'name':name,'owner_id':owner_id,'dtype':'<c16','shape':[size,size],'strides':[size*16,16],
                            'view_nbytes':count,'writeable':False,'base_chain':['numpy.ndarray','builtins.bytes'],
                            'byte_offset':0,'backing_span':[0,count],'sha256':'e'*64}
                        owners.append(owner);views.append(view);refs[owner_id]={'artifact':owner_id,'allocation_nbytes':count,'sha256':'e'*64}
                        desc[owner_id]={'dtype':'uint8','shape':[count],'payload_bytes':count}
            closed=stage=='cleanup';sealed=stage in ('all_sectors_retained_before_factor','apply_recovery_complete','cleanup')
            receipt={'stage':stage,'allocation_boundary':'shared_owner_receipt_'+stage,'scope':'named numerical backing allocations; not RSS',
                'owners':owners,'views':views,'owner_count':len(owners),'sum_view_nbytes_with_aliases':sum(v['view_nbytes'] for v in views),
                'unique_backing_owner_nbytes':sum(v['allocation_nbytes'] for v in owners),'templates':templates,
                'matrix_template_count':len(templates),'actual_state_count':len(templates),'lazy_inverse_count':sum(v['inverse_sha256'] is not None for v in templates),
                'sealed':sealed,'closed':closed,'basis_fingerprints':[{'basis_id':'basis','descriptor':{}}] if templates else [],'owner_artifacts':refs}
            if closed:receipt.update(cleanup_live_declared_owner_anchors=0,cleanup_all_declared_borrowers_released=True)
            stages.append(receipt);all_refs.update(refs)
        return {'schema':'task40extra.same80-shared-transform-equivalence.v1','roles':roles,'owner_stages':stages,'owner_artifacts':all_refs,
            'mapping_limit':1e-12,'shared_transforms':True,'same80_p4_only':True,'local_layout_borrows_existing_entities':True,
            'complete_before_any_factor':True,'payload_is_RSS':False,'target_savings_measured':False},desc

    def validate(self,evidence,desc):return self.checker['validate_shared_storage_metadata'](evidence,desc)

    def test_source_bridge_accepts_only_explicit_representation_scope(self):
        old,new,env=self.sources();receipt=self.bridge['validate_storage_source_bridge'](old,new,env,env)
        self.assertFalse(receipt['source_equality_claimed']);self.assertEqual(receipt['worker_head'],self.bridge['WORKER_HEAD'])

    def test_source_bridge_rejects_changed_physical_input(self):
        old,new,env=self.sources();new['files_sha256']['src/solvers/unchanged_physical.py']='f'*64
        with self.assertRaises(ValueError):self.bridge['validate_storage_source_bridge'](old,new,env,env)

    def test_source_bridge_rejects_deleted_dependency(self):
        old,new,env=self.sources();del new['files_sha256']['src/solvers/unchanged_physical.py']
        with self.assertRaises(ValueError):self.bridge['validate_storage_source_bridge'](old,new,env,env)

    def test_source_bridge_rejects_old_head_as_new_identity(self):
        old,new,env=self.sources();new['head']=old['head']
        with self.assertRaises(ValueError):self.bridge['validate_storage_source_bridge'](old,new,env,env)

    def test_source_bridge_rejects_abi_change(self):
        old,new,env=self.sources();other={**env,'petsc_int_type':'int64'}
        with self.assertRaises(ValueError):self.bridge['validate_storage_source_bridge'](old,new,env,other)

    def test_source_bridge_rejects_unpinned_worker_inventory(self):
        old,new,env=self.sources();old['files_sha256']['extra']='e'*64
        with self.assertRaises(ValueError):self.bridge['validate_storage_source_bridge'](old,new,env,env)

    def test_shared_plan_is_opt_in_and_still_not_run(self):
        plain=self.runner['plan_metadata']('solve');shared=self.runner['plan_metadata']('solve',shared_transforms=True)
        self.assertFalse(plain['shared_transforms']);self.assertTrue(shared['shared_transforms']);self.assertFalse(shared['PDE_solved'])

    def test_complete_metadata_fixture(self):
        proof,desc=self.evidence();self.assertTrue(self.validate(proof,desc))

    def test_empty_roles_do_not_pass(self):
        proof,desc=self.evidence();proof['roles']=[]
        with self.assertRaises(ValueError):self.validate(proof,desc)

    def test_missing_interior_record_does_not_pass(self):
        proof,desc=self.evidence();proof['roles'][0]['records'].pop()
        with self.assertRaises(ValueError):self.validate(proof,desc)

    def test_missing_six_direction_does_not_pass(self):
        proof,desc=self.evidence();proof['roles'][1]['directions'].pop()
        with self.assertRaises(ValueError):self.validate(proof,desc)

    def test_mutable_shared_view_does_not_pass(self):
        proof,desc=self.evidence();proof['owner_stages'][1]['views'][0]['writeable']=True
        with self.assertRaises(ValueError):self.validate(proof,desc)

    def test_alias_sum_is_independent_of_owner_sum(self):
        proof,desc=self.evidence();proof['owner_stages'][1]['sum_view_nbytes_with_aliases']+=16
        with self.assertRaises(ValueError):self.validate(proof,desc)

    def test_readonly_flag_without_immutable_backing_does_not_pass(self):
        proof,desc=self.evidence();proof['owner_stages'][1]['owners'][0]['owner_type']='numpy.ndarray'
        with self.assertRaises(ValueError):self.validate(proof,desc)

    def test_wrong_owner_bytes_do_not_pass(self):
        proof,desc=self.evidence();proof['owner_stages'][1]['unique_backing_owner_nbytes']+=1
        with self.assertRaises(ValueError):self.validate(proof,desc)

    def test_lazy_label_without_inverse_view_does_not_pass(self):
        proof,desc=self.evidence();stage=proof['owner_stages'][3];stage['views'].pop()
        stage['sum_view_nbytes_with_aliases']=sum(v['view_nbytes'] for v in stage['views'])
        with self.assertRaises(ValueError):self.validate(proof,desc)

    def test_missing_owner_artifact_does_not_pass(self):
        proof,desc=self.evidence();desc.pop(next(iter(desc)))
        with self.assertRaises(ValueError):self.validate(proof,desc)

    def test_missing_cleanup_does_not_pass(self):
        proof,desc=self.evidence();proof['owner_stages'].pop()
        with self.assertRaises(ValueError):self.validate(proof,desc)

    def test_live_cleanup_anchor_does_not_pass(self):
        proof,desc=self.evidence();proof['owner_stages'][-1]['cleanup_live_declared_owner_anchors']=1
        with self.assertRaises(ValueError):self.validate(proof,desc)

    def key_fixture(self):
        positions=list(range(192,300))
        basis={"actual_entity_positions":[[],[],[],[positions]],"matrix_dtype":"<c16"}
        key={"basis":"actual","dimension":3,"shape":[108,108],"channels":positions,
             "state":["cell_info",16],"semantics":["actual_element.Tt_apply","cell_dim_block_size","inverse_interior_block"],"dtype":"<c16"}
        witness={"dimension":3,"cell_info":16,"local_entity":None,"positions":positions}
        return key,witness,basis

    def check_key(self,key,witness,basis):
        return self.checker['validate_shared_record_key'](key,witness,dimension=3,size=108,basis_descriptor=basis,
            actual_cell_info=16,expected_state=["cell_info",16])

    def test_actual_cell_key_complete_identity(self):
        key,witness,basis=self.key_fixture();self.assertTrue(self.check_key(key,witness,basis))

    def test_actual_key_shape_dtype_channels_semantics_are_not_labels(self):
        for name,value in (("shape",[108,107]),("dtype","<f8"),("channels",list(reversed(range(192,300)))),
                           ("semantics",["identity"]),("state",["cell_info",17])):
            key,witness,basis=self.key_fixture();key[name]=value
            with self.subTest(name=name),self.assertRaises(ValueError):self.check_key(key,witness,basis)

    def test_actual_key_integer_and_channel_order_are_strict(self):
        key,witness,basis=self.key_fixture();key['state']=["cell_info",16.]
        with self.assertRaises(ValueError):self.check_key(key,witness,basis)

    def test_actual_witness_cannot_relabel_cell_orientation(self):
        key,witness,basis=self.key_fixture();witness['cell_info']=17
        with self.assertRaises(ValueError):self.check_key(key,witness,basis)

    def test_pipeline_factor_gate_and_default_branch_are_explicit(self):
        runner=RUNNER.read_text();probe=(ROOT/'src/solvers/y_orbit_two_cell_inverse_probe.py').read_text()
        self.assertIn('args.shared_transforms and not runtime_state["shared_equivalence_complete"]',runner)
        self.assertIn('entities=local_entities,transform_bank=bank',probe)
        self.assertIn("condensed=ids=default_entities=None",probe)
        self.assertIn('bank.close()', (ROOT/'src/solvers/y_orbit_shared_transform_evidence.py').read_text())

    def test_original_numerical_check_body_remains_distinct(self):
        text=CHECKER.read_text();self.assertIn('"original_check_count":len(checks)',text)
        self.assertIn('"shared_storage_checks":shared_checks',text)
        self.assertIn('default_prefix+"."+member,default_stage',text)
        self.assertIn('views[prefix+".rows"]["owner_id"]!=item["rows_owner_id"]',text)


if __name__=='__main__':unittest.main()
