"""Execute public-factory metadata branches without pretending PETSc/FE exists."""
import ast
from collections import defaultdict
from dataclasses import dataclass,field
import hashlib,importlib.util
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace
import unittest
import numpy as np

HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parents[1]
if HERE.name=='test' and HERE.parent.name=='src':
    CANDIDATE=HERE.parent/'solvers/p6_cell_condensed_action.py'
    ORIGINAL=HERE.parent/'solvers/original_port_blocks.py'
else:
    CANDIDATE=HERE/'NEW_UNQUALIFIED/src/solvers/p6_cell_condensed_action.py'
    ORIGINAL=WORKSPACE/'task40extra_cloud/recovered_v15/src/solvers/original_port_blocks.py'

def factory():
    # Extract exact production definitions, with only unavailable PETSc.IntType
    # and the final owned action constructor represented as metadata stubs.
    if hashlib.sha256(ORIGINAL.read_bytes()).hexdigest()!='de6940522d97343484851f7abe75dbb6302a3b64be2f0903cee3361bc9816645':
        raise ValueError('exact restored original-H source required')
    module=ModuleType('metadata_original_port_blocks');module.__file__=str(ORIGINAL)
    sys.modules[module.__name__]=module
    exec(compile(ORIGINAL.read_text(),str(ORIGINAL),'exec'),module.__dict__)
    tree=ast.parse(CANDIDATE.read_text())
    names={'_complex_vector','build_p6_cell_condensed_action_from_carrier'}
    classes={'P6CellPortTerms','P6DirectTracePortTerms'}
    body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)]
    body += [node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names
             or isinstance(node,ast.ClassDef) and node.name in classes]
    scope={'np':np,'PETSc':SimpleNamespace(IntType=np.int32),'defaultdict':defaultdict,
        'dataclass':dataclass,'field':field,'LEGACY_PORT_LAYOUT':'dense_legacy',
        'RESEARCH_PORT_LAYOUT':'cached_representation_research',
        'DiagonalOriginalPortBlock':module.DiagonalOriginalPortBlock,
        'DenseOriginalPortBlock':module.DenseOriginalPortBlock,
        'P6CellCondensedAction':lambda condensed,**kwargs:kwargs}
    exec(compile(ast.fix_missing_locations(ast.Module(body=body,type_ignores=[])),str(CANDIDATE),'exec'),scope)
    return scope['build_p6_cell_condensed_action_from_carrier'],module

def carrier(rows):
    h=1.2;key=(0,'top',0,0,'TE')
    identity={'mode_index':0,'side':'top','m':0,'n':0,'polarization':'TE',
              'projection_denominator':h}
    entry=SimpleNamespace(normalization_h=h,mode_key=key,mode_identity=identity,
        coupling_rows=rows,coupling_values=np.ones(len(rows),dtype=np.complex128),
        projection_rows=np.array([],dtype=np.int32),projection_values=np.array([],dtype=np.complex128))
    return SimpleNamespace(entries=(entry,))

def condensed():
    return SimpleNamespace(full_rows=2,appended_rows=1,cell_recovery_maps=(),
                          trace_constraints=SimpleNamespace(original_to_active={0:0,1:1}))

class PublicFactoryMetadataTests(unittest.TestCase):
    def test_count_overflow_stops_before_reading_carrier(self):
        fn,_=factory()
        class UnreadableCarrier:
            @property
            def entries(self):raise AssertionError('carrier must not be materialized')
        for name in ('full_rows','appended_rows'):
            c=condensed();setattr(c,name,int(np.iinfo(np.int32).max)+1)
            with self.subTest(name=name),self.assertRaises(OverflowError):
                fn(c,UnreadableCarrier(),port_block_layout='cached_representation_research')

    def test_wide_rows_fail_before_integer_conversion(self):
        fn,_=factory()
        for rows in (np.array([.2]),np.array([-1],dtype=np.int64),
                     np.array([2],dtype=np.int64),np.array([2**63+1],dtype=np.uint64)):
            with self.subTest(dtype=str(rows.dtype)),self.assertRaisesRegex(ValueError,'pre-cast'):
                fn(condensed(),carrier(rows),port_block_layout='cached_representation_research')

    def test_nominal_factory_binds_all_keys_and_H_values(self):
        fn,blocks=factory();c=carrier(np.array([0],dtype=np.int64))
        result=fn(condensed(),c,port_block_layout='cached_representation_research')
        self.assertIsNone(result['H_p'])
        self.assertEqual(result['original_port_block'].mode_keys,(c.entries[0].mode_key,))
        self.assertTrue(np.array_equal(result['original_port_block'].diagonal,np.array([1.2+0j])))
        bad=blocks.DiagonalOriginalPortBlock([2.4],(c.entries[0].mode_key,))
        with self.assertRaisesRegex(ValueError,'key/value'):
            fn(condensed(),c,port_block_layout='cached_representation_research',original_port_block=bad)

    def test_legacy_factory_keeps_existing_dense_default(self):
        fn,_=factory();result=fn(condensed(),carrier(np.array([0],dtype=np.int64)))
        self.assertTrue(np.array_equal(result['H_p'],np.array([[1.2+0j]])))
        self.assertIsNone(result['original_port_block'])
        self.assertEqual(result['port_block_layout'],'dense_legacy')


if __name__=='__main__':unittest.main(verbosity=2)
