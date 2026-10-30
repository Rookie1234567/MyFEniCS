"""Opt-in, immutable checkpoints for exact finite complex128 raw tensors.

The caller supplies the complete *scientific* identity of the tensor producer.
This store does not decide whether two materials, geometries or kernels are
physically equivalent. A damaged or incomplete existing entry is an error, not
permission to recompute or overwrite it. A manifest is committed last; no cache
entry can replace the independently required original-operator residual gate.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import stat
import time

_SCHEMA = "exact-raw-tensor-checkpoint.v1"
_CHUNK = 1024 * 1024
_MAX_JSON = 1024 * 1024
_FAILED_CLOSES = []


def _primitive(value):
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is list:
        return [_primitive(item) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {key: _primitive(item) for key, item in value.items()}
    raise TypeError("identity requires finite exact JSON primitives")


def canonical_identity(identity):
    """Type-preserving JSON bytes: 1, 1.0, True and -0.0 stay distinct."""
    if type(identity) is not dict or not identity:
        raise ValueError("a nonempty complete scientific identity is required")
    return json.dumps(_primitive(identity), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate manifest JSON key")
        result[key] = value
    return result


def _open_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("cache input must be a single-link regular file")
        return os.fdopen(fd, "rb"), info
    except BaseException as primary:
        try:
            os.close(fd)
        except BaseException as cleanup:
            primary.add_note("checkpoint descriptor close: " + repr(cleanup))
        raise


@contextmanager
def _owned_stream(stream):
    primary = None
    try:
        yield stream
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            stream.close()
        except BaseException as cleanup:
            _FAILED_CLOSES.append(stream)  # Never retry an uncertain close.
            if primary is None:
                raise
            primary.add_note("checkpoint stream close: " + repr(cleanup))


def _regular_json(path):
    stream, info = _open_regular(path)
    with _owned_stream(stream):
        if info.st_size > _MAX_JSON:
            raise ValueError("cache manifest exceeds its bounded JSON size")
        payload = stream.read(_MAX_JSON + 1)
        if len(payload) != info.st_size:
            raise ValueError("cache manifest changed while reading")
    value = json.loads(payload, object_pairs_hook=_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    return value, {"path": str(path), "bytes": len(payload), "sha256": sha256(payload).hexdigest()}


def _file_record(path):
    stream, info = _open_regular(path)
    digest = sha256()
    count = 0
    with _owned_stream(stream):
        while block := stream.read(_CHUNK):
            digest.update(block)
            count += len(block)
        after = os.fstat(stream.fileno())
    if count != info.st_size or (after.st_size, after.st_mtime_ns, after.st_ino) != (info.st_size, info.st_mtime_ns, info.st_ino):
        raise ValueError("checkpoint file changed while hashing")
    return {"path": str(path), "bytes": count, "sha256": digest.hexdigest()}


def _array_shape(shape, maximum):
    if type(shape) not in (tuple, list) or len(shape) != 2 or any(type(n) is not int or n <= 0 for n in shape):
        raise ValueError("a positive exact-integer two-dimensional shape is required")
    shape = tuple(shape)
    size = math.prod(shape) * 16
    if size > maximum:
        raise ValueError("tensor exceeds the declared byte budget")
    return shape, size


def _validate_array(array, shape):
    import numpy as np
    if type(array) is not np.ndarray or array.shape != shape or array.dtype.str != "<c16" or not array.flags.c_contiguous:
        raise TypeError("producer must return an exact C-contiguous little-endian complex128 ndarray")
    flat = array.reshape(-1)
    for start in range(0, flat.size, _CHUNK // 16):
        if not bool(np.isfinite(flat[start:start + _CHUNK // 16]).all()):
            raise ValueError("nonfinite raw tensor")
    digest = sha256()
    view = memoryview(array).cast("B")
    for start in range(0, len(view), _CHUNK):
        digest.update(view[start:start + _CHUNK])
    return digest.hexdigest()


def _read_tensor(path, shape, *, load):
    """Check the header before allocating; hash and finite-check all payload."""
    import numpy as np
    stream, info = _open_regular(path)
    expected_bytes = math.prod(shape) * 16
    with _owned_stream(stream):
        version = np.lib.format.read_magic(stream)
        if version == (1, 0):
            header_shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream, max_header_size=4096)
        elif version == (2, 0):
            header_shape, fortran, dtype = np.lib.format.read_array_header_2_0(stream, max_header_size=4096)
        else:
            raise ValueError("unsupported NPY header version")
        offset = stream.tell()
        if header_shape != shape or fortran or dtype.str != "<c16" or info.st_size != offset + expected_bytes:
            raise ValueError("checkpoint NPY header/length differs from declared tensor")
        stream.seek(0)
        whole = sha256(stream.read(offset))
        payload = sha256()
        array = np.empty(shape, dtype="<c16", order="C") if load else None
        target = memoryview(array).cast("B") if load else None
        consumed = 0
        while consumed < expected_bytes:
            block = stream.read(min(_CHUNK, expected_bytes - consumed))
            if not block or len(block) % 16:
                raise ValueError("truncated complex128 payload")
            if not bool(np.isfinite(np.frombuffer(block, dtype="<c16")).all()):
                raise ValueError("nonfinite checkpoint tensor")
            whole.update(block)
            payload.update(block)
            if target is not None:
                target[consumed:consumed + len(block)] = block
            consumed += len(block)
        after = os.fstat(stream.fileno())
        if stream.read(1) or (after.st_size, after.st_mtime_ns, after.st_ino) != (info.st_size, info.st_mtime_ns, info.st_ino):
            raise ValueError("checkpoint tensor changed while reading")
    return array, {"bytes": info.st_size, "sha256": whole.hexdigest(),
                   "payload_sha256": payload.hexdigest(), "shape": list(shape),
                   "dtype": "<c16", "order": "C", "header_version": list(version)}


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    primary = None
    try:
        os.fsync(fd)
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            os.close(fd)
        except BaseException as cleanup:
            _FAILED_CLOSES.append(("directory", str(path), fd))
            if primary is None:
                raise
            primary.add_note("checkpoint directory close: " + repr(cleanup))


def _publish_no_replace(temporary, final):
    # Hard-link publication is atomic and refuses an existing destination.
    os.link(temporary, final, follow_symlinks=False)
    temporary.unlink()
    _sync_directory(final.parent)


class ExactTensorCheckpoint:
    """Single-owner store. Memory and disk allowances are caller-visible.

    A cold commit needs at most one tensor-sized disk file (link publication
    does not copy data), plus a bounded header/JSON allowance. Validation uses
    1 MiB read buffers, not a second full tensor. Warm loads allocate one tensor.
    The caller's live-RSS admission remains mandatory and is not replaced here.
    """
    def __init__(self, directory, *, max_tensor_bytes=32 * 2**20,
                 disk_reserve_bytes=2 * 2**30):
        if type(max_tensor_bytes) is not int or max_tensor_bytes <= 0 or type(disk_reserve_bytes) is not int or disk_reserve_bytes < 0:
            raise ValueError("exact nonnegative disk reserve and positive tensor budget required")
        path = Path(directory).absolute()
        if path != path.resolve(strict=False):
            raise ValueError("checkpoint directory must have canonical non-symlink parents")
        path.mkdir(parents=True, exist_ok=True)
        if path.is_symlink() or not path.is_dir():
            raise ValueError("checkpoint root is not a regular directory")
        self.directory = path
        self.max_tensor_bytes = max_tensor_bytes
        self.disk_reserve_bytes = disk_reserve_bytes

    def get_or_compute(self, identity, shape, compute):
        started = time.monotonic()
        encoded = canonical_identity(identity)
        if len(encoded) > _MAX_JSON // 2:
            raise ValueError("scientific identity exceeds its bounded size")
        frozen_identity = json.loads(encoded)
        key = sha256(encoded).hexdigest()
        shape, tensor_bytes = _array_shape(shape, self.max_tensor_bytes)
        entry = self.directory / key
        tensor_path, manifest_path = entry / "tensor.npy", entry / "manifest.json"
        try:
            info = entry.lstat()
        except FileNotFoundError:
            info = None
        if info is not None:
            if not stat.S_ISDIR(info.st_mode) or entry.is_symlink() or set(p.name for p in entry.iterdir()) != {"tensor.npy", "manifest.json"}:
                raise ValueError("existing checkpoint entry is incomplete, aliased or has unknown members")
            manifest, manifest_record = _regular_json(manifest_path)
            if (type(manifest) is not dict or set(manifest) != {"schema", "key", "identity", "tensor"}
                    or manifest["schema"] != _SCHEMA or manifest["key"] != key
                    or canonical_identity(manifest["identity"]) != encoded):
                raise ValueError("checkpoint scientific identity differs")
            array, tensor = _read_tensor(tensor_path, shape, load=True)
            if json.dumps(tensor, sort_keys=True, separators=(",", ":")) != json.dumps(manifest["tensor"], sort_keys=True, separators=(",", ":"), allow_nan=False):
                raise ValueError("checkpoint tensor header/content identity differs")
            compute_seconds = 0.0
            cache_hit = True
        else:
            if not callable(compute):
                raise TypeError("cold checkpoint requires its original compute callback")
            free = os.statvfs(self.directory)
            free_bytes = free.f_bavail * free.f_frsize
            required = tensor_bytes + _MAX_JSON + self.disk_reserve_bytes
            if free_bytes < required:
                raise RuntimeError("checkpoint disk reserve admission failed")
            compute_started = time.monotonic()
            array = compute()
            compute_seconds = time.monotonic() - compute_started
            expected_payload = _validate_array(array, shape)
            if canonical_identity(identity) != encoded:
                raise ValueError("compute callback mutated the scientific identity")
            # A long cold kernel may outlive the first disk observation.
            free = os.statvfs(self.directory)
            if free.f_bavail * free.f_frsize < required:
                raise RuntimeError("checkpoint disk reserve changed before commit")
            entry.mkdir()  # Refuse a competing writer or an existing partial entry.
            temporary = entry / "tensor.npy.building"
            import numpy as np
            with _owned_stream(temporary.open("xb")) as stream:
                np.lib.format.write_array(stream, array, version=(1, 0), allow_pickle=False)
                stream.flush()
                os.fsync(stream.fileno())
            _unused, tensor = _read_tensor(temporary, shape, load=False)
            if tensor["payload_sha256"] != expected_payload:
                raise ValueError("written checkpoint differs from computed tensor")
            _publish_no_replace(temporary, tensor_path)
            manifest = {"schema": _SCHEMA, "key": key, "identity": frozen_identity, "tensor": tensor}
            payload = (json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
            if len(payload) > _MAX_JSON:
                raise ValueError("checkpoint manifest exceeds its bound")
            temporary = entry / "manifest.json.building"
            with _owned_stream(temporary.open("xb")) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            _publish_no_replace(temporary, manifest_path)
            manifest_record = _file_record(manifest_path)
            if manifest_record["sha256"] != sha256(payload).hexdigest():
                raise ValueError("published manifest differs from committed bytes")
            _sync_directory(self.directory)
            cache_hit = False
        if canonical_identity(identity) != encoded:
            raise ValueError("scientific identity changed during checkpoint access")
        receipt = {"schema": _SCHEMA, "key": key, "cache_hit": cache_hit,
                   "compute_seconds": compute_seconds, "elapsed_seconds": time.monotonic() - started,
                   "tensor_bytes": tensor_bytes, "maximum_io_buffer_bytes": _CHUNK,
                   "disk_reserve_bytes": self.disk_reserve_bytes,
                   "tensor": tensor, "records": [
                       {"path": str(tensor_path), "bytes": tensor["bytes"], "sha256": tensor["sha256"]},
                       manifest_record], "independent_original_residual_still_required": True}
        return array, receipt
