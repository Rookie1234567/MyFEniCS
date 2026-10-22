#!/usr/bin/env python3
"""Fixed, explicitly approved cleanup only. No recursive removal or retries."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time

BASE = Path('/workspace/scratch/9c465670b46b')
RECOVERY = BASE / 'recovery_20261018_0935'
MANIFEST = BASE / 'archive_20261022/publish/docs/task40extra_dot_parallel_cloud/outcomes/archive_20261022/cleanup_candidates.json'
MANIFEST_SHA = '2fbcabeaacf30abab22d40c710a66768cc5ea2f05472f5f54451b7da5541c218'
REMOTE_COMMIT = '250f837e5e44436ee87e6d39d36a3f274e96afb7'
LOCK = RECOVERY / 'scaled07_hp216_solver_preparation02/hy_formal.lock'
B = RECOVERY / 'scaled07_hp216_mixed_bubble_preparation03/stageB'
OUT = BASE / 'archive_20261022/cleanup_execution01'
FENCE = [(LOCK, 1185952, None), (B/'capacity06', 1315266, None),
         (B/'capacity06.command.json', 1315267, '25d4941062cd1826ad15c3df5aa469c23cce0dbd2d73a46b1222f090fdc56ae4'),
         (B/'capacity06/terminal.json', 1315268, '23f84d4b8ab2e54d6cd58e494b42312895da1500be4e0edb433c596adc59d509')]

def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def identity(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_nlink, s.st_size,
            s.st_mtime_ns, s.st_ctime_ns)

def sha_fd(fd):
    h = hashlib.sha256()
    while True:
        b = os.read(fd, 8 << 20)
        if not b:
            return h.hexdigest()
        h.update(b)

def parent_fd(rel):
    p = Path(rel)
    require(not p.is_absolute() and '..' not in p.parts and p.parts[0] == RECOVERY.name, 'path containment')
    fd = os.open(BASE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in p.parts[:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd, p.name
    except BaseException:
        os.close(fd)
        raise

def verify_file(row):
    d, name = parent_fd(row['path'])
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=d)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'not regular single-link')
            require((before.st_size, before.st_mtime_ns, stat.S_IMODE(before.st_mode)) ==
                    (row['bytes'], row['mtime_ns'], row['mode']), 'manifest stat mismatch')
            require(sha_fd(fd) == row['sha256'], 'candidate digest mismatch')
            require(identity(os.fstat(fd)) == identity(before), 'changed during hash')
            require(identity(os.stat(name, dir_fd=d, follow_symlinks=False)) == identity(before), 'entry changed')
            return identity(before)
        finally:
            os.close(fd)
    finally:
        os.close(d)

def check_fence():
    for p, inode, digest in FENCE:
        s = p.lstat()
        require((s.st_dev, s.st_ino) == (27, inode) and not p.is_symlink(), 'live fence identity')
        if digest:
            require(hashlib.sha256(p.read_bytes()).hexdigest() == digest, 'live fence digest')
    require(sorted(p.name for p in (B/'capacity06').iterdir()) == ['terminal.json'], 'fence contents')

def retained_snapshot(excluded):
    out = {}
    for root, dirs, files in os.walk(RECOVERY, followlinks=False):
        for name in dirs + files:
            p = Path(root)/name
            rel = str(p.relative_to(BASE))
            if rel in excluded:
                continue
            s = p.lstat()
            if stat.S_ISDIR(s.st_mode):
                value = (s.st_dev, s.st_ino, s.st_mode)  # parent timestamps legitimately change
            else:
                value = identity(s) + ((os.readlink(p) if stat.S_ISLNK(s.st_mode) else None),)
            out[rel] = value
    return out

def write_all(fd, b):
    view = memoryview(b)
    while view:
        n = os.write(fd, view)
        require(n > 0, 'short journal write')
        view = view[n:]

def emit(fd, obj):
    write_all(fd, (json.dumps(obj, sort_keys=True) + '\n').encode())
    os.fsync(fd)

def save_new(path, obj):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        emit(fd, obj)
    finally:
        os.close(fd)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--approval-message-id')
    args = ap.parse_args()
    require(args.execute and args.approval_message_id, 'explicit parent-relayed approval required; no default mutation')
    raw = MANIFEST.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == MANIFEST_SHA, 'fixed manifest changed')
    data = json.loads(raw)
    rows = [r for g in data['groups'] for r in g['files']]
    paths = {r['path'] for r in rows}
    require(len(rows) == len(paths) == 648 and sum(r['bytes'] for r in rows) == 4680932836, 'fixed scope/count/bytes')
    for row in rows:
        parts = Path(row['path']).parts
        require(not any(v in parts for v in ('.git', 'repo', 'lib', 'bin', 'site-packages', 'dist-packages')), 'protected scope')
        require(Path(row['path']).suffix in ('.npz', '.npy', '.o', '.so'), 'non-candidate suffix')
    require(not OUT.exists(), 'prior cleanup outcome exists; no retry')
    lockfd = os.open(LOCK, os.O_RDWR | os.O_NOFOLLOW)
    journal = None
    completed = []
    try:
        require((os.fstat(lockfd).st_dev, os.fstat(lockfd).st_ino) == (27, 1185952), 'lock identity')
        fcntl.flock(lockfd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check_fence()
        baseline = retained_snapshot(paths)
        pins = {r['path']: verify_file(r) for r in rows}  # all bytes before any deletion
        retained_c = {r['path']: verify_file(r) for r in data['retained_generated_c_source_evidence']}
        require(hashlib.sha256(MANIFEST.read_bytes()).hexdigest() == MANIFEST_SHA, 'manifest changed after preflight')
        require(retained_snapshot(paths) == baseline, 'retained objects changed before mutation')
        check_fence()
        OUT.mkdir(mode=0o700)
        dirfd = os.open(OUT, os.O_RDONLY | os.O_DIRECTORY)
        parent = os.open(OUT.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
            save_new(OUT/'retained_before.json', baseline)
            journal = os.open(OUT/'journal.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.fsync(dirfd)
            free_before = os.statvfs(BASE).f_bavail * os.statvfs(BASE).f_frsize
            emit(journal, {'event':'START', 'approval_message_id':args.approval_message_id,
                          'remote_commit':REMOTE_COMMIT, 'manifest_sha256':MANIFEST_SHA,
                          'count':648, 'logical_bytes':4680932836, 'time_ns':time.time_ns()})
            for row in rows:
                d, name = parent_fd(row['path'])
                try:
                    require(identity(os.stat(name, dir_fd=d, follow_symlinks=False)) == pins[row['path']], 'fresh identity mismatch')
                    emit(journal, {'event':'INTENT', 'path':row['path'], 'identity':pins[row['path']], 'bytes':row['bytes']})
                    require(identity(os.stat(name, dir_fd=d, follow_symlinks=False)) == pins[row['path']], 'identity changed after intent')
                    os.unlink(name, dir_fd=d)
                    os.fsync(d)
                    emit(journal, {'event':'DELETED', 'path':row['path'], 'bytes':row['bytes']})
                    completed.append(row)
                finally:
                    os.close(d)
            require(retained_snapshot(paths) == baseline, 'protected object change after cleanup')
            for row in data['retained_generated_c_source_evidence']:
                require(verify_file(row) == retained_c[row['path']], 'retained generated source changed')
            check_fence()
            require(all(not (BASE/p).exists() and not (BASE/p).is_symlink() for p in paths), 'candidate still exists')
            free_after = os.statvfs(BASE).f_bavail * os.statvfs(BASE).f_frsize
            receipt = {'status':'COMPLETE', 'approval_message_id':args.approval_message_id,
                       'remote_commit':REMOTE_COMMIT, 'manifest_sha256':MANIFEST_SHA,
                       'deleted_files':len(completed), 'deleted_logical_bytes':sum(r['bytes'] for r in completed),
                       'filesystem_free_delta_bytes':free_after-free_before,
                       'free_delta_is_not_exclusive_attribution':True, 'retained_objects_unchanged':True,
                       'live_fence_retained':True, 'original_owner_exit_status':'UNKNOWN', 'time_ns':time.time_ns()}
            save_new(OUT/'receipt.json', receipt)
            os.fsync(dirfd)
            print(json.dumps(receipt), flush=True)
        finally:
            os.close(parent)
            os.close(dirfd)
    except BaseException as exc:
        if journal is not None:
            emit(journal, {'event':'STOP', 'error_type':type(exc).__name__, 'error':str(exc),
                           'confirmed_deleted_files':len(completed),
                           'confirmed_deleted_logical_bytes':sum(r['bytes'] for r in completed),
                           'pending_intent_may_require_reconciliation':True})
        raise
    finally:
        if journal is not None:
            os.close(journal)
        os.close(lockfd)  # releases only this caller's flock

if __name__ == '__main__':
    main()
