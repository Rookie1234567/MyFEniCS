"""Research-only causal FP64 prediction/XOR VectorBank. No FE or solver."""
import ctypes
import hashlib
import json
import platform
import struct
import sys
import time
import zlib
from pathlib import Path

import numpy as np

MAGIC = b'WB48\x00\x01'
MASK = (1 << 64) - 1


def abi():
    return {'machine': platform.machine(), 'byteorder': sys.byteorder,
            'numpy': np.__version__, 'libc': list(platform.libc_ver()),
            'python': list(sys.version_info[:2]), 'math_threads': 1}


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Backend:
    def __init__(self, registration):
        self.registration = registration
        self.name = registration['name']
        if self.name == 'zstd':
            path = Path(registration['library'])
            if digest(path.read_bytes()) != registration['sha256']:
                raise ValueError('codec library identity')
            self.lib = ctypes.CDLL(str(path))
            self.lib.ZSTD_compressBound.argtypes = [ctypes.c_size_t]
            self.lib.ZSTD_compressBound.restype = ctypes.c_size_t
            for name in ('ZSTD_compress', 'ZSTD_decompress'):
                fn = getattr(self.lib, name)
                fn.restype = ctypes.c_size_t
                fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t] + ([ctypes.c_int] if name == 'ZSTD_compress' else [])
            self.lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
            self.lib.ZSTD_isError.restype = ctypes.c_uint
        elif self.name != 'zlib' or registration['version'] != zlib.ZLIB_RUNTIME_VERSION:
            raise ValueError('codec backend ABI')

    def compress(self, data, level=3):
        if self.name == 'zlib':
            return zlib.compress(data, 6)
        out = ctypes.create_string_buffer(self.lib.ZSTD_compressBound(len(data)))
        source = ctypes.create_string_buffer(data)
        n = self.lib.ZSTD_compress(out, len(out), source, len(data), level)
        if self.lib.ZSTD_isError(n):
            raise ValueError('zstd encoding')
        return out.raw[:n]

    def decompress(self, data, length):
        if length < 0 or length > 256 * 60 * 16:
            raise ValueError('bounded entity block length')
        if self.name == 'zlib':
            out = zlib.decompress(data)
        else:
            outbuf, source = ctypes.create_string_buffer(length), ctypes.create_string_buffer(data)
            n = self.lib.ZSTD_decompress(outbuf, length, source, len(data))
            if self.lib.ZSTD_isError(n) or n != length:
                raise ValueError('zstd decoding length')
            out = outbuf.raw[:n]
        if len(out) != length:
            raise ValueError('codec decoded length')
        return out


def layout(keys, sizes, offsets, ntrace):
    keys, sizes, offsets = np.asarray(keys), np.asarray(sizes), np.asarray(offsets)
    if len(offsets) == len(sizes)+1:
        offsets = offsets[:-1]
    blocks = []
    for kind in (1, 2):
        for axis in (0, 1, 2):
            nodes = np.flatnonzero((keys[:, 0] == kind) & (keys[:, 1] == axis) & (offsets < ntrace))
            nodes = sorted(nodes, key=lambda n: tuple(keys[n]))
            for start in range(0, len(nodes), 256):
                subset = nodes[start:start + 256]
                p = 6 if kind == 1 else 60
                if any(sizes[n] != p for n in subset):
                    raise ValueError('complete original entity moments')
                rows = [[int(offsets[n] + i) for i in range(p)] for n in subset]
                blocks.append({'kind': kind, 'axis': axis, 'rows': rows})
    flat = sorted(i for b in blocks for entity in b['rows'] for i in entity)
    if flat != list(range(ntrace)):
        raise ValueError('complete trace permutation inventory')
    return blocks


def causal_features(previous, kind, axis, moment, total):
    """Eight normalized past values, four static features; no future/label."""
    scale = np.maximum(1e-30, np.max(abs(previous), axis=1))
    feat = np.zeros((len(previous), 12), np.float64)
    feat[:, :8] = (previous / scale[:, None]).view(np.float64).reshape(-1, 8)
    feat[:, 8:] = [kind - 1, axis / 2, moment / (total - 1), total / 60]
    return feat, scale, np.all(previous == 0, axis=1)


def infer(features, weights):
    if len(weights) == 2:
        return features @ weights[0].T + weights[1]
    hidden = np.tanh(features @ weights[0].T + weights[1])
    hidden = np.tanh(hidden @ weights[2].T + weights[3])
    return hidden @ weights[4].T + weights[5]


def learned_transform(values, block, weights, *, decode=False):
    """Same NumPy operations for encoder and decoder, reset each entity."""
    words = np.asarray(values, dtype='<u8').copy().reshape(len(block['rows']), -1, 2)
    original = np.zeros_like(words)
    p = words.shape[1]
    raw_count = 0
    for m in range(p):
        if m == 0:
            original[:, m] = words[:, m]
            raw_count += len(words)
            continue
        past = np.zeros((len(words), 4), complex)
        take = min(m, 4)
        # Original/decoded past only; no use of current original in prediction.
        past[:, -take:] = original[:, m-take:m].copy().reshape(len(words), take*2).view(np.complex128)
        features, scale, raw = causal_features(past, block['kind'], block['axis'], m, p)
        predicted = infer(features, weights) * scale[:, None]
        if not np.isfinite(predicted).all():
            raise ValueError('nonfinite prediction: explicit block fallback required')
        predicted[raw] = 0
        pred_words = np.ascontiguousarray(predicted).view('<u8').reshape(-1, 2)
        raw_count += int(raw.sum())
        if decode:
            original[:, m] = words[:, m] ^ pred_words
        else:
            original[:, m] = words[:, m]
            words[:, m] ^= pred_words
    return (original if decode else words).reshape(-1).tobytes(), raw_count


def context_transform(data, method, *, decode=False):
    words = np.frombuffer(data, '<u8')
    out = np.empty_like(words)
    table = np.zeros(4096, np.uint64) if method != 'PREV' else None
    context = last = 0
    for i, value in enumerate(words):
        prediction = last if method == 'PREV' else int(table[context]) if method == 'FCM' else (last + int(table[context])) & MASK
        original = int(value) ^ prediction if decode else int(value)
        out[i] = original if decode else original ^ prediction
        delta = (original - last) & MASK
        if table is not None:
            table[context] = delta if method == 'DFCM' else original
        context = ((context << 5) ^ ((delta if method == 'DFCM' else original) >> 48)) & 4095
        last = original
    return out.tobytes()


def shuffle(data, *, inverse=False):
    b = np.frombuffer(data, np.uint8)
    return (b.reshape(8, -1).T if inverse else b.reshape(-1, 8).T).copy().tobytes()


def write_bank(path, vectors, blocks, method, backend, weights=()):
    begin = time.perf_counter()
    method_name, level = method, 3
    if method.startswith(('BYTE:', 'SHUFFLE:')):
        method_name, level = method.split(':')
        level = int(level)
    payload = bytearray()
    index, statistics = [], []
    for vector in vectors:
        if vector.dtype != np.dtype('complex128') or vector.ndim != 1:
            raise ValueError('complete complex128 input')
        entries = []
        for b in blocks:
            values = np.ascontiguousarray(vector[np.asarray(b['rows'])])
            raw = values.tobytes()
            fallback = not np.isfinite(values).all()
            raw_count = 0
            if method_name == 'RAW' or fallback:
                encoded, actual = raw, 'RAW'
            else:
                if method_name == 'SHUFFLE':
                    transformed = shuffle(raw)
                elif method_name in ('PREV', 'FCM', 'DFCM'):
                    transformed = context_transform(raw, method_name)
                elif method_name in ('LIN', 'NN'):
                    try:
                        transformed, raw_count = learned_transform(values.view('<u8'), b, weights)
                    except ValueError:
                        fallback = True
                        transformed = raw
                else:
                    transformed = raw
                encoded = raw if fallback else backend.compress(transformed, level)
                actual = 'RAW' if fallback else method_name
            entries.append({'offset': len(payload), 'length': len(encoded), 'raw_length': len(raw),
                            'codec': actual, 'raw_sha256': digest(raw), 'encoded_sha256': digest(encoded),
                            'fallback': fallback, 'raw_anchor_or_zero_past': raw_count})
            payload.extend(encoded)
            statistics.append({'bytes': len(encoded), 'raw_bytes': len(raw), 'kind': b['kind'], 'axis': b['axis'], 'fallback': fallback})
        index.append(entries)
    weights_metadata = []
    for w in weights:
        data = np.ascontiguousarray(w, np.float64).tobytes()
        weights_metadata.append({'offset': len(payload), 'length': len(data), 'shape': list(w.shape), 'sha256': digest(data)})
        payload.extend(data)
    header = {'schema': 'lossless-vector-bank48-v1', 'abi': abi(), 'method': method,
              'vectors': len(vectors), 'ntrace': len(vectors[0]), 'blocks': blocks,
              'index': index, 'backend': backend.registration, 'weights': weights_metadata,
              'whole_original_hashes': [digest(np.ascontiguousarray(v).tobytes()) for v in vectors]}
    encoded_header = json.dumps(header, separators=(',', ':'), allow_nan=False).encode()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = MAGIC + struct.pack('<I', len(encoded_header)) + encoded_header + payload
    temporary = path.with_suffix('.partial')
    temporary.write_bytes(blob)
    temporary.replace(path)
    return {'path': str(path), 'sha256': digest(blob), 'file_bytes': len(blob),
            'payload_bytes': sum(x['length'] for v in index for x in v),
            'model_bytes': sum(x.nbytes for x in weights), 'header_bytes': len(encoded_header),
            'raw_bytes': sum(v.nbytes for v in vectors), 'encoding_seconds': time.perf_counter()-begin,
            'block_statistics': statistics}


class VectorBank:
    """One resident compressed byte bank, one output workspace, no source path."""
    def __init__(self, path, expected_hash, *, expected_abi=None):
        data = Path(path).read_bytes()
        if digest(data) != expected_hash or data[:len(MAGIC)] != MAGIC:
            raise ValueError('bank bytes/hash')
        n = struct.unpack_from('<I', data, len(MAGIC))[0]
        if n > 4*2**20 or len(data) < len(MAGIC) + 4 + n:
            raise ValueError('bank header bound')
        start = len(MAGIC) + 4 + n
        self.header = json.loads(data[len(MAGIC)+4:start])
        if self.header['abi'] != (abi() if expected_abi is None else expected_abi):
            raise ValueError('bank inference ABI/endian mismatch')
        self.payload = data[start:]
        self.backend = Backend(self.header['backend'])
        self.weights = []
        for w in self.header['weights']:
            bits = memoryview(self.payload)[w['offset']:w['offset']+w['length']]
            if digest(bits) != w['sha256']:
                raise ValueError('model hash')
            self.weights.append(np.frombuffer(bits, '<f8').reshape(w['shape']))
        self.rows = [np.asarray(b['rows'], np.int64) for b in self.header['blocks']]
        rows = sorted(i for r in self.rows for i in r.ravel())
        if rows != list(range(self.header['ntrace'])):
            raise ValueError('stored canonical permutation inventory')
        self.raw = None
        if self.header['method'] == 'RAW':
            # RAW loaded directly into its canonical resident bank; get is view.
            self.raw = np.asarray([self._decode(i) for i in range(self.header['vectors'])])
            self.payload = b''

    def _decode(self, i):
        out = np.empty(self.header['ntrace'], complex)
        for block, ids, entry in zip(self.header['blocks'], self.rows, self.header['index'][i], strict=True):
            data = self.payload[entry['offset']:entry['offset']+entry['length']]
            if len(data) != entry['length'] or digest(data) != entry['encoded_sha256']:
                raise ValueError('truncated/corrupt bank block')
            codec = entry['codec']
            if codec != 'RAW':
                data = self.backend.decompress(data, entry['raw_length'])
                if codec == 'SHUFFLE':
                    data = shuffle(data, inverse=True)
                elif codec in ('PREV', 'FCM', 'DFCM'):
                    data = context_transform(data, codec, decode=True)
                elif codec in ('LIN', 'NN'):
                    data, _ = learned_transform(np.frombuffer(data, '<u8'), block, self.weights, decode=True)
            if digest(data) != entry['raw_sha256']:
                raise ValueError('decoded original block hash')
            out[ids] = np.frombuffer(data, np.complex128).reshape(ids.shape)
        if digest(out.tobytes()) != self.header['whole_original_hashes'][i]:
            raise ValueError('whole trace bit identity')
        return out

    def get(self, i):
        return self.raw[i] if self.raw is not None else self._decode(i)

    def object_bytes(self):
        # Explicit dynamic resident loads + compulsory one decoder/current buffer.
        n = self.header['ntrace'] * 16
        mapping = sum(sys.getsizeof(x) for x in self.rows)
        header = python_bytes(self.header)
        raw_payload = sys.getsizeof(self.raw) if self.raw is not None else sys.getsizeof(self.payload)
        max_block = max(x.size for x in self.rows) * 16
        # Upper planning bound for block transformation/ctypes/shuffle copies,
        # learned activations/features, uint64 context table and one decoded
        # vector. Scalars/current/axpy block are common to RAW and compressed.
        workspace = 0 if self.raw is not None else n + 12*max_block + 256*32*8*4 + (4096*8 if self.header['method'] in ('FCM', 'DFCM') else 0)
        model = sum(sys.getsizeof(x) for x in self.weights) + sys.getsizeof(self.weights)
        common = n + 256*16 + self.header['vectors']*2*16
        return {'resident_bank_bytes': raw_payload + mapping + header + model,
                'compulsory_workspace_bytes': workspace + common,
                'complete_trace_bank_object_bytes': raw_payload + mapping + header + model + workspace + common,
                'accounting': 'resident Python-owned headers/rows/model views plus bounded workspace upper plan; interpreter/library/allocator included separately in process-tree RSS'}


def python_bytes(value, seen=None):
    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(python_bytes(k, seen) + python_bytes(v, seen) for k, v in value.items())
    elif isinstance(value, (list, tuple)):
        size += sum(python_bytes(x, seen) for x in value)
    return size


def consume(bank):
    """Two fixed complete traversals; vdot then axpy, no Krylov iteration."""
    began = time.perf_counter()
    n = bank.header['ntrace']
    current = np.zeros(n, complex)
    scalars = []
    for order in (range(bank.header['vectors']), range(bank.header['vectors']-1, -1, -1)):
        for i in order:
            vector = bank.get(i)
            scalars.append(np.vdot(vector, current))
            scalar = complex((i+1)/32, (i % 3 - 1)/64)
            # Same arithmetic order for RAW and compressed. No full third
            # vector and no mutation of the RAW resident view.
            for start in range(0, n, 256):
                end = min(n, start+256)
                current[start:end] += scalar * vector[start:end]
    return np.asarray(scalars), current, time.perf_counter()-began
