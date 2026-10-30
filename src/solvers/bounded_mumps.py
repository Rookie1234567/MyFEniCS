"""Explicit public symbolic/numeric boundary for memory-gated exact MUMPS.

The shim only fills MatFactorInfo using the installed headers. Object ownership,
controls, INFOG and solves stay in public petsc4py. No private structs or PC math.
"""
from __future__ import annotations
import ctypes
from hashlib import sha256
import json
from math import ceil
import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import shlex
import time

FAILED_OWNERS = []


def _digest(path):
    h=sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(2**20),b""): h.update(block)
    return h.hexdigest()


def load_public_shim(directory):
    from petsc4py import PETSc
    import numpy as np
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    source=Path(__file__).with_name("public_mumps_stages.c")
    prefix=Path(sys.prefix).resolve()
    header=prefix/"include/petscmat.h"
    library=(prefix/"lib/libpetsc.so").resolve(strict=True)
    compiler=shlex.split(sysconfig.get_config_var("CC") or "")
    if not compiler or Path(compiler[0]).parent!=prefix/"bin" or not any(x.startswith("--sysroot=") for x in compiler):
        raise RuntimeError("explicit qualified relocated compiler policy must be active")
    facts={"schema":"public-petsc-mumps-stages.v1","source_sha256":_digest(source),
           "header_sha256":_digest(header),"library_sha256":_digest(library),
           "PETSc_version":list(PETSc.Sys.getVersion()),"prefix":str(prefix),
           "compiler":compiler,"compiler_sha256":_digest(compiler[0]),
           "configuration_headers":{name:_digest(prefix/"include"/name)
                for name in ("petscconf.h","petscsys.h","petscmat.h","petscversion.h")}}
    key=sha256(json.dumps(facts,sort_keys=True).encode()).hexdigest()
    output=directory/("public_mumps_"+key+".so")
    depfile=directory/(key+".d")
    dependencies=directory/(key+".dependencies.json")
    command=compiler+["-std=c99","-O2","-fPIC","-shared","-MD","-MF",str(depfile),str(source),
             "-I"+str(prefix/"include"),"-L"+str(prefix/"lib"),
             "-Wl,-rpath,"+str(prefix/"lib"),"-lpetsc","-o",str(output)]
    if not output.exists():
        # One supervised owner; fail without loading a partial compilation.
        temporary=output.with_suffix(".building.so")
        if temporary.exists(): raise RuntimeError("stale public-shim build output")
        build=command[:-1]+[str(temporary)]
        done=subprocess.run(build,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        (directory/(key+".build.json")).write_text(json.dumps({"argv":build,"returncode":done.returncode,
             "stdout":done.stdout,"stderr":done.stderr},indent=2))
        if done.returncode: raise RuntimeError("public PETSc shim compilation failed")
        # Compiler-emitted complete transitive header dependency identity.
        dependency_paths=shlex.split(depfile.read_text().replace("\\\n", " ").split(":",1)[1])
        dependency_records=[{"path":str(Path(p).resolve()),"sha256":_digest(p)} for p in dependency_paths]
        dependencies.write_text(json.dumps(dependency_records,indent=2))
        os.replace(temporary,output)
    for item in json.loads(dependencies.read_text()):
        if _digest(item["path"])!=item["sha256"]:raise RuntimeError("compiled public-shim dependency changed")
    api=ctypes.CDLL(str(output))
    for name in ("myfenics_mumps_symbolic","myfenics_mumps_numeric"):
        function=getattr(api,name);function.argtypes=[ctypes.c_void_p,ctypes.c_void_p];function.restype=ctypes.c_int
    for name in ("myfenics_petsc_int_bytes","myfenics_petsc_scalar_bytes"):
        getattr(api,name).argtypes=[];getattr(api,name).restype=ctypes.c_int
    if (api.myfenics_petsc_int_bytes()!=np.dtype(PETSc.IntType).itemsize
            or api.myfenics_petsc_scalar_bytes()!=np.dtype(PETSc.ScalarType).itemsize
            or np.dtype(PETSc.ScalarType)!=np.dtype("complex128")):
        raise RuntimeError("compiled PETSc ABI differs from loaded petsc4py")
    facts.update(shim_file=str(output),shim_sha256=_digest(output),compile_argv=command,
                 dependencies_file=str(dependencies),dependencies_sha256=_digest(dependencies))
    return api,facts


class PublicMumpsFactor:
    def __init__(self,matrix,api,*,controls):
        from petsc4py import PETSc
        self.matrix=matrix;self.api=api;self.pc=None;self.factor=None
        self.symbolic_done=False;self.numeric_done=False;self.close_attempted=False;self.close_error=None
        self.pc=PETSc.PC().create(matrix.getComm())
        try:
            self.pc.setOperators(matrix);self.pc.setType("lu");self.pc.setFactorSolverType("mumps")
            self.pc.setFactorSetUpSolverType()
            self.factor=self.pc.getFactorMatrix()
            for key,value in controls.items():self.factor.setMumpsIcntl(int(key),int(value))
            self.controls={str(k):int(self.factor.getMumpsIcntl(int(k))) for k in controls}
            if self.controls!={str(k):int(v) for k,v in controls.items()}:raise RuntimeError("MUMPS control readback")
        except BaseException as exc:
            try:self.close()
            except BaseException as cleanup:exc.add_note("factor cleanup: "+repr(cleanup))
            raise

    def symbolic(self):
        if self.symbolic_done or self.close_attempted:raise RuntimeError("symbolic lifecycle")
        code=self.api.myfenics_mumps_symbolic(self.factor.handle,self.matrix.handle)
        if code:raise RuntimeError(f"MatLUFactorSymbolic error {code}")
        self.symbolic_done=True
        return {str(i):int(self.factor.getMumpsInfog(i)) for i in (1,2,3,4,16,17,26,27)}

    def numeric(self):
        if not self.symbolic_done or self.numeric_done or self.close_attempted:raise RuntimeError("numeric lifecycle")
        code=self.api.myfenics_mumps_numeric(self.factor.handle,self.matrix.handle)
        if code:raise RuntimeError(f"MatLUFactorNumeric error {code}")
        self.numeric_done=True

    def solve(self,b,x):
        if not self.numeric_done or self.close_attempted:raise RuntimeError("solve lifecycle")
        self.factor.solve(b,x)

    def close(self):
        if self.close_attempted:
            if self.close_error is not None:raise self.close_error
            return
        self.close_attempted=True
        try:
            if self.factor is not None:self.factor.destroy();self.factor=None
            if self.pc is not None:self.pc.destroy();self.pc=None
        except BaseException as exc:
            self.close_error=exc;FAILED_OWNERS.append(self);raise


def symbolic_memory_preflight(matrix, options, *, admit, directory):
    """Temporary symbolic only, same numerical controls as the later KSP.

    Estimates are not RSS bounds: reserve two times the larger INFOG memory
    estimate plus 256 MiB and an independent caller margin. Numeric re-analysis
    is explicitly counted and is not a reused factor.
    """
    api,identity=load_public_shim(directory)
    controls={14:100,24:1,35:0,22:0}
    for key,value in options.items():
        if key.startswith("mat_mumps_icntl_"):controls[int(key.rsplit("_",1)[1])]=int(value)
    if controls.get(35)!=0 or controls.get(22)!=0:raise ValueError("exact in-core MUMPS only")
    admit("mumps_symbolic",512*2**20,estimate_basis="symbolic workspace policy reserve; actual monitor remains binding")
    factor=None;primary=None;started=time.monotonic()
    try:
        factor=PublicMumpsFactor(matrix,api,controls=controls)
        info=factor.symbolic()
        if info["1"]<0:raise RuntimeError("MUMPS symbolic INFOG failure")
        estimate_mb=max(info["16"],info["26"])
        if estimate_mb<=0:raise RuntimeError("missing positive MUMPS symbolic memory estimate")
        future=ceil(2*estimate_mb*1_000_000)+256*2**20
        cap_mb=ceil(future/1_000_000)
        record={"schema":"mumps-symbolic-preflight.v1","INFOG":info,"controls":factor.controls,
                "shim":identity,"future_numeric_bytes":future,"numeric_ICNTL23_MB":cap_mb,
                "numeric_calls":0,"symbolic_seconds":time.monotonic()-started,
                "estimate_not_upper_bound":True,"later_KSP_repeats_symbolic":True}
        Path(directory,"symbolic_preflight.json").write_text(json.dumps(record,indent=2,allow_nan=False))
    except BaseException as exc:primary=exc;raise
    finally:
        if factor is not None:
            try:factor.close()
            except BaseException as cleanup:
                if primary is None:raise
                primary.add_note("symbolic factor cleanup: "+repr(cleanup))
    admit("mumps_numeric",future,estimate_basis=record)
    return record
