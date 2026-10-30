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


def incore_memory_budget(info, nnz, observation, *, available_floor_bytes):
    """MUMPS 5.8.2 in-core policy; INFOG16 already includes ICNTL14.

    ICNTL23 caps MUMPS workspace only, NOT process RSS. PETSc conversion is
    conservatively charged 24 bytes per stored entry (two indices plus a value
    copy even when complex-double SeqAIJ aliases values), plus 256 MiB outside
    MUMPS. The independent 512 MiB stage margin is never lent to the factor.
    """
    if type(nnz) is not int or nnz < 1 or type(available_floor_bytes) is not int or available_floor_bytes < 2**30:
        raise ValueError("positive exact nnz and >=1GiB available floor required")
    need=info["16"]
    values=[need,observation["effective_cap_bytes"],observation["live_tree_and_supervisor_bytes"],
            observation["system"]["available"],observation["margin_bytes"]]
    if any(type(v) is not int or v < 0 for v in values) or need < 1 or values[-1] < 512*2**20:
        raise ValueError("finite exact integer live memory/INFOG16 observations required")
    external=24*nnz+256*2**20
    available=min(min(values[1],10_000_000_000)-values[2], values[3]-available_floor_bytes)
    observation_slack=16*2**20
    workspace_budget=available-values[4]-external-observation_slack
    cap_mb=workspace_budget//1_000_000
    return {"policy":"mumps582-incore-live-workspace-cap-v2",
            "required_INFOG16_MB":need,"INFOG26_OOC_diagnostic_only":info["26"],
            "matrix_stored_nnz":nnz,"petsc_conversion_upper_bytes":24*nnz,
            "outside_mumps_reserve_bytes":256*2**20,"external_future_bytes":external,
            "independent_margin_bytes":values[4],"available_floor_bytes":available_floor_bytes,
            "uncommitted_observation_slack_bytes":observation_slack,
            "live_observation":observation,"workspace_budget_bytes":workspace_budget,
            "numeric_ICNTL23_MB":cap_mb,"future_numeric_bytes":max(0,cap_mb)*1_000_000+external,
            "passed":cap_mb>=need,"estimate_not_upper_bound":True,
            "MUMPS_cap_not_process_RSS_cap":True,
            "reference":"MUMPS 5.8.2 user guide section 5.11; PETSc v3.25.6 MatConvertToTriples_seqaij_seqaij"}


def symbolic_memory_preflight(matrix, options, *, admit, directory):
    """Same in-core controls as the later KSP, before any numeric factor.

    INFOG16 includes the selected ICNTL14. ICNTL23 is selected from observed
    live headroom after releasing this temporary symbolic factor, with separate
    PETSc conversion reserve and the unchanged stage/supervisor safety gates.
    Ordinary KSP repeats symbolic; no factor reuse or changed ordering claimed.
    """
    from ..common.strict_json import atomic_json
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
        if info["1"]<0 or info["16"]<=0:raise RuntimeError("MUMPS symbolic INFOG failure or missing in-core estimate")
        record={"schema":"mumps-symbolic-preflight.v2","INFOG":info,"controls":factor.controls,
                "shim":identity,"numeric_calls":0,"symbolic_seconds":time.monotonic()-started,
                "estimate_not_upper_bound":True,"later_KSP_repeats_symbolic":True}
        atomic_json(Path(directory,"symbolic_preflight.json"),record)
    except BaseException as exc:primary=exc;raise
    finally:
        if factor is not None:
            try:factor.close()
            except BaseException as cleanup:
                if primary is None:raise
                primary.add_note("symbolic factor cleanup: "+repr(cleanup))
    nz=matrix.getInfo()["nz_used"]
    if isinstance(nz,bool) or not float(nz).is_integer() or nz<1:raise RuntimeError("invalid actual stored nnz")
    observation=admit("mumps_numeric_budget_observation",0,
                      estimate_basis="symbolic factor released; observe actual live headroom before choosing ICNTL23")
    budget=incore_memory_budget(info,int(nz),observation,
                               available_floor_bytes=int(os.environ["TASK44_AVAILABLE_FLOOR_BYTES"]))
    record.update(budget)
    atomic_json(Path(directory,"symbolic_preflight.json"),record)
    if not budget["passed"]:raise RuntimeError("MUMPS_INCORE_WORKSPACE_CAP_BELOW_ANALYSIS_REQUIREMENT")
    admit("mumps_numeric",budget["future_numeric_bytes"],estimate_basis=record)
    return record
