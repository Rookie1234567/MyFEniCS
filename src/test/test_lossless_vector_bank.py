"""Small actual codec/consumer/identity negative witnesses. No old arrays."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from benchmarks.check_vector_bank import literal_check, reference_consumer
from src.solvers.lossless_vector_bank import Backend, VectorBank, abi, consume, context_transform, learned_transform, shuffle, write_bank
from src.solvers.vector_storage_scope import assert_snapshot


class CodecTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'nested/test.bank'
        self.backend=Backend({'name':'zlib','version':__import__('zlib').ZLIB_RUNTIME_VERSION})
        self.blocks=[{'kind':1,'axis':0,'rows':[[0,1,2,3,4,5],[6,7,8,9,10,11]]}]
        rng=np.random.default_rng(48)
        self.vectors=np.asarray(rng.normal(size=(3,12))+1j*rng.normal(size=(3,12)),np.complex128)
        self.weights=[rng.normal(size=(2,12)),rng.normal(size=2)]

    def tearDown(self):
        self.tmp.cleanup()

    def bank(self,method):
        r=write_bank(self.path,self.vectors,self.blocks,method,self.backend,self.weights if method=='LIN' else ())
        return VectorBank(self.path,r['sha256']),r

    def test_all_registered_transforms_and_consumer_bits(self):
        expected=reference_consumer(self.vectors)
        for method in ('RAW','BYTE:3','BYTE:19','SHUFFLE:3','SHUFFLE:19','PREV','FCM','DFCM','LIN'):
            bank,_=self.bank(method)
            self.assertTrue(literal_check(bank,self.vectors))
            values,current,_=consume(bank)
            self.assertEqual(values.tobytes(),expected[0].tobytes())
            self.assertEqual(current.tobytes(),expected[1].tobytes())
            if method=='RAW':
                self.assertTrue(np.shares_memory(bank.get(0),bank.raw))

    def test_special_bits_fallback(self):
        words=self.vectors.view('<u8')
        words.ravel()[:8]=[0,1<<63,1,0x8000000000000001,0x7ff0000000000000,0x7ff8000000000042,0xfff8000000000013,0x000fffffffffffff]
        for method in ('RAW','SHUFFLE:3','FCM','DFCM','LIN'):
            bank,_=self.bank(method);self.assertTrue(literal_check(bank,self.vectors))
            self.assertTrue(bank.header['index'][0][0]['fallback'])

    def test_context_integer_exact(self):
        bits=self.vectors.view('<u8').tobytes()
        for method in ('PREV','FCM','DFCM'):
            self.assertEqual(context_transform(context_transform(bits,method),method,decode=True),bits)
        self.assertEqual(shuffle(shuffle(bits),inverse=True),bits)

    def test_causality_future_change_does_not_change_first_prediction(self):
        before=self.vectors[0].view('<u8').copy()
        later=before.copy();later[8:12]^=np.uint64(17)
        a,_=learned_transform(before,self.blocks[0],self.weights)
        b,_=learned_transform(later,self.blocks[0],self.weights)
        self.assertEqual(a[:64],b[:64])
        self.assertEqual(learned_transform(np.frombuffer(a,'<u8'),self.blocks[0],self.weights,decode=True)[0],before.tobytes())

    def test_zero_previous_raw_and_anchor(self):
        self.vectors[:]=0
        bank,_=self.bank('LIN');self.assertTrue(literal_check(bank,self.vectors))
        self.assertEqual(bank.header['index'][0][0]['raw_anchor_or_zero_past'],12)

    def test_corrupt_truncated_and_endian(self):
        _,r=self.bank('BYTE:3')
        with self.assertRaisesRegex(ValueError,'hash'):
            VectorBank(self.path,'0'*64)
        with self.assertRaisesRegex(ValueError,'ABI/endian'):
            VectorBank(self.path,r['sha256'],expected_abi=dict(abi(),byteorder='big'))
        self.path.write_bytes(self.path.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError,'hash'):
            VectorBank(self.path,r['sha256'])

    def test_no_original_read_and_shuffled_counterexample(self):
        bank,_=self.bank('LIN')
        with patch('numpy.load',side_effect=AssertionError('original forbidden')),patch('pathlib.Path.open',side_effect=AssertionError('original forbidden')):
            consume(bank)
        with self.assertRaisesRegex(ValueError,'bits differ'):
            literal_check(bank,self.vectors[::-1])

    def test_same_HEAD_wrong_snapshot_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'snapshot'):
            assert_snapshot('same','same',{'a':'old'},{'a':'changed'},'')
        with self.assertRaises(RuntimeError):
            assert_snapshot('same','same',{'a':'old'},{'a':'old'},'dirty')
        assert_snapshot('same','same',{'a':'old'},{'a':'old'},'')

    def test_live_frozen_storage(self):
        from src.runners.port_preparation import storage_limits
        self.assertEqual(storage_limits('v48')['task_storage_bytes'],24*2**30)
        self.assertEqual(storage_limits('v48')['new_storage_bytes'],2**30)
        self.assertEqual(json.loads(Path('input/task042_neural_coarse_inverse/vector_storage_v48.json').read_text())['A_AH_B'],0)


if __name__=='__main__':
    unittest.main()
