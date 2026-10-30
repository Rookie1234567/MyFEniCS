"""Same-process loaded-file origin/hash/ABI gate. Never constructs FE objects.

Call arm_native_runtime_identity() BEFORE first MPI import. After scientific
imports (and again after JIT/factor), call require_native_runtime_identity().
Source pins are caller-owned; generated_records allow exact files, not folders.
This is a current-process snapshot, not a future-import or full-runtime-tree proof.
The singleton MPICH shared-data check is copied from the actually qualified
2026-10-30 import probe helper; it is NOT a /dev/shm library allowlist.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import importlib.machinery
import json
import os
import re
import stat
import sys
import time


def need(condition, reason):
    if not condition:
        raise RuntimeError(reason)


SYSTEM_LIB_NAMES=('ld-linux-x86-64.so.2','libc.so.6','libm.so.6','libpthread.so.0','libdl.so.2','librt.so.1','libresolv.so.2','libutil.so.1','libnss_files.so.2','libnss_dns.so.2')
SYSTEM_MAP_ALLOWLIST={str(Path(root)/name) for root in ('/usr/lib/x86_64-linux-gnu','/lib/x86_64-linux-gnu') for name in SYSTEM_LIB_NAMES}
SYSTEM_MAP_ALLOWLIST.update(('/lib64/ld-linux-x86-64.so.2','/usr/lib64/ld-linux-x86-64.so.2','/usr/lib/locale/C.utf8/LC_CTYPE','/usr/lib/x86_64-linux-gnu/gconv/gconv-modules.cache'))

MPI_SHARED_DATA_STATE = None
MPI_SHARED_DATA_DIAGNOSTICS = []

def arm_native_runtime_identity():
    global MPI_SHARED_DATA_STATE
    need(MPI_SHARED_DATA_STATE is None and 'mpi4py.MPI' not in sys.modules, 'mpi_data_arm_before_first_import')
    need(not any(k in os.environ for k in ('PMI_SIZE','PMI_PORT','PMI_ID','PMIX_NAMESPACE')), 'mpi_data_singleton_launch_required')
    expected = Path('/dev/shm') / f'mpich_shm_{os.getpid():x}_0'
    need(not os.path.lexists(expected), 'mpi_data_preexisting_object_refused')
    mount = [line.split() for line in Path('/proc/self/mountinfo').read_text().splitlines() if line.split()[4] == '/dev/shm']
    need(len(mount) == 1 and mount[0][mount[0].index('-')+1] == 'tmpfs', 'mpi_data_tmpfs_mount_required')
    mountinfo_device = tuple(int(v) for v in mount[0][2].split(':'))
    directory_stat = Path('/dev/shm').lstat()
    need(stat.S_ISDIR(directory_stat.st_mode) and not Path('/dev/shm').is_symlink(), 'mpi_data_shm_directory_identity')
    mount_device = (os.major(directory_stat.st_dev), os.minor(directory_stat.st_dev))
    baseline = []
    for line in Path('/proc/self/maps').read_text().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6:
            baseline.append((fields[3], fields[4], fields[5]))
    MPI_SHARED_DATA_STATE = {'path':str(expected), 'pid':os.getpid(), 'uid':os.geteuid(), 'not_present_before_import':True, 'mount_device':mount_device, 'mountinfo_device':mountinfo_device, 'mountinfo_raw':' '.join(mount[0]), 'directory_stat':{'st_dev':directory_stat.st_dev,'major':mount_device[0],'minor':mount_device[1],'inode':directory_stat.st_ino,'mode':directory_stat.st_mode}, 'preimport_maps':baseline, 'armed_time_ns':time.time_ns()}
    return MPI_SHARED_DATA_STATE

def singleton_mpi_shared_data_gate(fields, raw, resolved):
    state = MPI_SHARED_DATA_STATE
    diagnostic = {'raw_map_fields':list(fields), 'raw_map_line':' '.join(fields), 'raw_path':str(raw), 'resolved_path':str(resolved), 'preimport_state':state, 'checked_time_ns':time.time_ns()}
    MPI_SHARED_DATA_DIAGNOSTICS.append(diagnostic)
    try:
        observed = raw.lstat()
        diagnostic['object_lstat'] = {key:getattr(observed,key) for key in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_ctime_ns','st_mtime_ns')}
        diagnostic['object_device'] = [os.major(observed.st_dev),os.minor(observed.st_dev)]
        diagnostic['parsed_map_device'] = [int(v,16) for v in fields[3].split(':')]
        diagnostic['parsed_map_inode'] = int(fields[4])
    except BaseException as error:
        diagnostic['observation_error'] = type(error).__name__+':'+str(error)
    if state is None or str(raw) != state['path']:
        return None
    need(raw == resolved and not raw.is_symlink() and raw.parent == Path('/dev/shm'), 'mpi_data_exact_nonsymlink_path')
    need(fields[1] == 'rw-s' and int(fields[2],16) == 0, 'mpi_data_nonexec_shared_offset_zero')
    need((fields[3],fields[4],fields[5]) not in state['preimport_maps'], 'mpi_data_not_new_mapping')
    map_device = tuple(int(v,16) for v in fields[3].split(':'))
    need(map_device == state['mount_device'] and int(fields[4]) > 0, 'mpi_data_tmpfs_map_device')
    before = raw.lstat()
    need(stat.S_ISREG(before.st_mode) and not (before.st_mode & 0o111) and before.st_uid == state['uid'] and before.st_nlink == 1, 'mpi_data_file_type_owner_mode')
    need((os.major(before.st_dev),os.minor(before.st_dev)) == map_device and before.st_ino == int(fields[4]), 'mpi_data_map_stat_identity')
    now = time.time_ns()
    need(state['armed_time_ns'] <= before.st_ctime_ns <= now and state['armed_time_ns'] <= before.st_mtime_ns <= now, 'mpi_data_created_during_this_import')
    start,end = (int(v,16) for v in fields[0].split('-'))
    page = os.sysconf('SC_PAGE_SIZE')
    need(0 < before.st_size <= end-start <= ((before.st_size+page-1)//page)*page, 'mpi_data_exact_mapping_extent')
    fd = os.open(raw, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        actual = os.fstat(fd)
        need((actual.st_dev,actual.st_ino,actual.st_size,actual.st_ctime_ns,actual.st_mtime_ns) == (before.st_dev,before.st_ino,before.st_size,before.st_ctime_ns,before.st_mtime_ns), 'mpi_data_open_identity_changed')
        header = os.read(fd,4)
        diagnostic['object_fstat'] = {key:getattr(actual,key) for key in ('st_dev','st_ino','st_mode','st_uid','st_nlink','st_size','st_ctime_ns','st_mtime_ns')}
        diagnostic['header_hex'] = header.hex()
        need(header != b'\x7fELF', 'mpi_data_ELF_refused')
    finally:
        os.close(fd)
    return {'classification':'current_singleton_MPICH_shared_data_not_library','pid':state['pid'],'uid':state['uid'],'path':str(raw),'perms':fields[1],'offset':fields[2],'map_device':fields[3],'inode':before.st_ino,'file_bytes':before.st_size,'map_bytes':end-start,'mode':stat.S_IMODE(before.st_mode),'ctime_ns':before.st_ctime_ns,'mtime_ns':before.st_mtime_ns,'armed_time_ns':state['armed_time_ns'],'preimport_absent':True,'preimport_mapping_absent':True,'filesystem':'tmpfs','filesystem_type_evidence':state['mountinfo_raw'],'mountinfo_reported_device':state['mountinfo_device'],'directory_stat_device':state['mount_device'],'ELF_magic':False,'prefix_or_library_allowlist_expansion':False}


MEMBER_PREFIX = "task40extra_cloud/p8_balh_experiment/runtime"
REQUIRED_MODULES = ("numpy", "scipy", "mpi4py.MPI", "dolfinx", "dolfinx_mpc", "basix",
                    "ffcx", "ufl", "petsc4py.PETSc", "slepc4py.SLEPc")
SCIENTIFIC_ROOTS = {name.split(".")[0] for name in REQUIRED_MODULES} | {"cffi", "_cffi_backend"}


def _file_identity(path):
    """Stream hashing with stable open/stat identity, no full-file byte copy."""
    path = Path(path)
    need(path.is_absolute() and path.resolve(strict=True) == path, "canonical_file_required:" + str(path))
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode), "nonregular_file:" + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        need(signature(before) == signature(opened), "file_changed_before_hash:" + str(path))
        value = hashlib.file_digest(stream, "sha256").hexdigest()
        need(signature(opened) == signature(os.fstat(stream.fileno())) == signature(path.lstat()),
             "file_changed_during_hash:" + str(path))
    return {"path": str(path), "bytes": before.st_size, "sha256": value,
            "device": [os.major(before.st_dev), os.minor(before.st_dev)], "inode": before.st_ino}


def _descriptor_map(records, label):
    output = {}
    for row in records:
        need(set(row) == {"path", "bytes", "sha256"}, label + "_exact_descriptor_schema")
        path = Path(row["path"])
        need(path.is_absolute() and path.resolve(strict=True) == path, label + "_canonical_nonsymlink_path")
        need(type(row["bytes"]) is int and row["bytes"] >= 0 and
             isinstance(row["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]),
             label + "_invalid_bytes_or_sha")
        need(str(path) not in output, label + "_duplicate_file")
        output[str(path)] = dict(row)
    return output


def require_native_runtime_identity(runtime_prefix, member_manifest, generated_records=(), *,
                                    member_manifest_sha256, preimport_state, source_records=()):
    """Require loaded native files and all module origins to match pinned inputs.

    runtime_prefix: canonical restored prefix, with sys.executable == prefix/bin/python.
    member_manifest: existing 20261030 regular-member JSON, caller SHA-pinned.
    generated_records/source_records: exact {path,bytes,sha256} lists. Project
    Python sources use source_records; newly built JIT/shim native images use
    generated_records. Neither list grants directory-wide native permission.
    preimport_state: the SAME in-process object returned by arm_native_runtime_identity.
    """
    prefix, manifest_path = Path(runtime_prefix), Path(member_manifest)
    need(prefix.is_absolute() and prefix.resolve(strict=True) == prefix, "canonical_runtime_prefix")
    need(Path(sys.prefix) == prefix and Path(sys.executable) == prefix / "bin/python", "wrong_python_prefix_or_executable")
    need(sys.flags.optimize == 0, "optimized_python_disallowed")
    need(preimport_state is MPI_SHARED_DATA_STATE and preimport_state is not None and
         preimport_state["pid"] == os.getpid(), "same_process_preimport_arm_required")
    manifest_identity = _file_identity(manifest_path)
    need(manifest_identity["sha256"] == member_manifest_sha256, "runtime_member_manifest_sha_mismatch")
    expected = json.loads(manifest_path.read_text())
    need(isinstance(expected, dict) and MEMBER_PREFIX + "/bin/python3.12" in expected, "wrong_member_manifest_layout")
    generated = _descriptor_map(generated_records, "generated")
    sources = _descriptor_map(source_records, "source")
    need(not set(generated) & set(sources), "source_generated_identity_overlap")
    for name in generated:
        need(not Path(name).is_relative_to(prefix) and name not in SYSTEM_MAP_ALLOWLIST,
             "generated_record_cannot_override_runtime_or_system")
        actual = _file_identity(Path(name))
        need(actual["bytes"] == generated[name]["bytes"] and actual["sha256"] == generated[name]["sha256"],
             "generated_artifact_identity_mismatch:" + name)
    for name in REQUIRED_MODULES:
        need(name in sys.modules and sys.modules[name] is not None, "required_native_module_not_loaded:" + name)
    np, petsc, mpi = (sys.modules[name] for name in ("numpy", "petsc4py.PETSc", "mpi4py.MPI"))
    need(np.dtype(petsc.ScalarType) == np.dtype("complex128") and np.dtype(petsc.IntType) == np.dtype("int32"), "wrong_PETSc_scalar_or_integer")
    need(petsc.COMM_WORLD.size == 1 and mpi.COMM_WORLD.Get_size() == 1, "MPI1_required")
    need(tuple(petsc.Sys.getVersion()) == (3, 25, 6), "PETSc_version_changed_from_qualified_runtime")
    files = {}

    def verify(path, category):
        resolved = path.resolve(strict=True)
        key = str(resolved)
        if key not in files:
            record = _file_identity(resolved)
            if category == "runtime":
                relative = MEMBER_PREFIX + "/" + str(resolved.relative_to(prefix))
                need(relative in expected, "loaded_runtime_file_absent_from_manifest:" + relative)
                want = expected[relative]
            elif category == "generated":
                want = generated[key]
            elif category == "source":
                want = sources[key]
            else:
                want = None  # Explicit system allowlist; record current bytes, not pretend archived.
            if want is not None:
                need(record["bytes"] == want["bytes"] and record["sha256"] == want["sha256"],
                     "loaded_file_identity_mismatch:" + key)
            record.update(category=category, aliases=[])
            files[key] = record
        need(files[key]["category"] == category, "conflicting_file_classification:" + key)
        if str(path) not in files[key]["aliases"]:
            files[key]["aliases"].append(str(path))
        return key

    maps, shared = [], []
    maps_text = Path("/proc/self/maps").read_text()
    for line in maps_text.splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) != 6 or not fields[5].startswith("/"):
            continue
        raw = Path(fields[5])
        need(not fields[5].endswith(" (deleted)"), "deleted_loaded_file:" + fields[5])
        resolved = raw.resolve(strict=True)
        if raw.is_relative_to(prefix) and resolved.is_relative_to(prefix):
            category = "runtime"
        elif str(raw) in SYSTEM_MAP_ALLOWLIST and str(resolved) in SYSTEM_MAP_ALLOWLIST:
            category = "system_allowlist"
        elif str(raw) == str(resolved) and str(resolved) in generated:
            category = "generated"
        else:
            mpi_data = singleton_mpi_shared_data_gate(fields, raw, resolved)
            need(mpi_data is not None, "mapped_file_outside_explicit_native_inputs:" + str(raw))
            shared.append(mpi_data)
            continue
        key = verify(raw, category)
        record = files[key]
        need(record["device"] == [int(v, 16) for v in fields[3].split(":")] and
             record["inode"] == int(fields[4]), "mapped_inode_differs_from_hashed_file:" + str(raw))
        maps.append({"address": fields[0], "permissions": fields[1], "offset": fields[2],
                     "device": fields[3], "inode": int(fields[4]), "raw": str(raw), "file": key})

    module_rows = []
    source_dirs = {str(Path(path).parent) for path in sources}
    for name, module in sorted(list(sys.modules.items())):
        if module is None:
            continue
        spec = getattr(module, "__spec__", None)
        candidates = []
        origin, filename = getattr(spec, "origin", None), getattr(module, "__file__", None)
        if origin is not None:
            candidates.append(("spec_origin", origin))
        if filename is not None:
            candidates.append(("file", filename))
        candidates.extend(("package_path", v) for v in list(getattr(module, "__path__", ())))
        checked = []
        for kind, value in candidates:
            if kind == "spec_origin" and value in ("built-in", "frozen"):
                checked.append({"kind": kind, "value": value})
                continue
            raw = Path(os.fspath(value))
            need(raw.is_absolute(), "nonabsolute_module_origin:" + name + ":" + str(raw))
            resolved = raw.resolve(strict=True)
            native = any(str(raw).endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES)
            if raw.is_relative_to(prefix) and resolved.is_relative_to(prefix):
                category = "runtime"
            elif kind != "package_path" and str(raw) == str(resolved) and str(resolved) in generated:
                category = "generated"
            else:
                need(name.split(".")[0] not in SCIENTIFIC_ROOTS and not native,
                     "scientific_module_outside_runtime_or_generated:" + name)
                permitted = source_dirs if kind == "package_path" else sources
                need(str(raw) == str(resolved) and str(raw) in permitted, "unpinned_source_module:" + name + ":" + str(raw))
                category = "source"
            key = verify(raw, category) if kind != "package_path" else str(resolved)
            checked.append({"kind": kind, "raw": str(raw), "resolved": key, "category": category})
        module_rows.append({"module": name, "origins": checked, "no_filesystem_origin_declared": not candidates})
    # Hash inputs again, not a claimed guarantee against modifications after return.
    need(_file_identity(manifest_path)["sha256"] == member_manifest_sha256, "member_manifest_changed_during_audit")
    return {"schema": "same-process-native-runtime-identity-v1", "status": "PASS_CURRENT_PROCESS_SNAPSHOT",
            "pid": os.getpid(), "python": {"executable": sys.executable, "prefix": sys.prefix, "version": sys.version},
            "runtime_prefix": str(prefix), "member_manifest": manifest_identity,
            "scalar": "complex128", "integer": "int32", "MPI_size": 1, "PETSc": list(petsc.Sys.getVersion()),
            "MPI_library": mpi.Get_library_version(), "loaded_files": sorted(files.values(), key=lambda row: row["path"]),
            "loaded_maps": maps, "maps_text_sha256": hashlib.sha256(maps_text.encode()).hexdigest(),
            "module_origins": module_rows, "mpi_shared_data": shared,
            "generated_records": list(generated.values()), "source_record_count": len(sources),
            "system_map_allowlist": sorted(SYSTEM_MAP_ALLOWLIST),
            "scope": "same-process loaded files and origins only; not PDE qualification or a future-import guarantee"}
