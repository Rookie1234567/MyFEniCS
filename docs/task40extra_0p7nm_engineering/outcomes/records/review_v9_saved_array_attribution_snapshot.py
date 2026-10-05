"""One-shot independent attribution of the frozen W1 boundary arrays."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import basix
import basix.ufl
import mpmath as mp
import numpy as np
from src.solvers.task40_w1_moment_reference import legendre_exponential_moments

ROOT = Path.cwd()
ART = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w9_wsl"
RAW = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w1_wsl/w1_probe_c354afa_retry1_20261004T1654Z/probe/w1_boundary_probe_arrays.npz"
MANIFEST = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5/original_size_auto_mode_manifest.json"
RAW_SHA = "a475bba1618abd74981622a66e127b2fd88b43f52a2339f5087115ed9b1a82f8"
MANIFEST_SHA = "52d7ec801de65d11b15aa1b6daff8d2ad43e1f51902dfd91d06597e49715490d"
KEY_SHA = "03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec"

def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def z(value):
    return complex(value["real"], value["imag"]) if isinstance(value, dict) else complex(value)

def active_dofs(element, side):
    topo = basix.cell.topology(basix.CellType.hexahedron)
    face = 0 if side == "bottom" else 5
    vertices = set(topo[2][face])
    edges = [e for e, vs in enumerate(topo[1]) if set(vs) <= vertices]
    return np.asarray(
        [int(d) for e in edges for d in element.entity_dofs[1][e]]
        + [int(d) for d in element.entity_dofs[2][face]], dtype=np.int64
    )

def face_map(element, side, i, j, nx, ny, phases, trace_size):
    """Rebuild Basix entity ownership and periodic row mapping independently."""
    p = int(element.degree)
    active = active_dofs(element, side)
    lookup = {int(d): n for n, d in enumerate(active)}
    side_id = 0 if side == "bottom" else 1
    side_rows = 2 * p**2 * nx * ny
    rows = np.full(len(active), -1, dtype=np.int64)
    weights = np.ones(len(active), dtype=np.complex128)
    ref = basix.cell.geometry(basix.CellType.hexahedron)
    topo = basix.cell.topology(basix.CellType.hexahedron)
    for edge, vertices in enumerate(topo[1]):
        ids = [int(d) for d in element.entity_dofs[1][edge]]
        if not ids or ids[0] not in lookup:
            continue
        pts = ref[list(vertices)]
        if pts[0, 0] != pts[1, 0]:
            jj = j + int(pts[0, 1]); block = 0
            entity = i * ny + (jj % ny)
            phase = phases[1] if jj == ny else 1.0 + 0.0j
        else:
            ii = i + int(pts[0, 0]); block = nx * ny * p
            entity = (ii % nx) * ny + j
            phase = phases[0] if ii == nx else 1.0 + 0.0j
        for order, dof in enumerate(ids):
            pos = lookup[dof]
            rows[pos] = side_id * side_rows + block + entity * p + order
            weights[pos] = phase
    face = 0 if side == "bottom" else 5
    face_ids = [int(d) for d in element.entity_dofs[2][face]]
    offset = 2 * nx * ny * p + (i * ny + j) * len(face_ids)
    for order, dof in enumerate(face_ids):
        rows[lookup[dof]] = side_id * side_rows + offset + order
    if np.any(rows < 0) or np.any(rows >= trace_size) or len(np.unique(rows)) != len(rows):
        raise ValueError("independent face map is incomplete or out of range")
    return active, rows, weights

def main():
    if sha(RAW) != RAW_SHA or sha(MANIFEST) != MANIFEST_SHA:
        raise ValueError("frozen raw or manifest SHA mismatch")
    modes = json.loads(MANIFEST.read_text())["modes"]
    keys = [[r["side"], r["m"], r["n"], r["polarization"]] for r in modes]
    key_hash = hashlib.sha256(json.dumps(keys, separators=(",", ":")).encode()).hexdigest()
    if len(modes) != 32060 or key_hash != KEY_SHA:
        raise ValueError("frozen ordered keys mismatch")
    with np.load(RAW, allow_pickle=False) as data:
        raw = {name: data[name] for name in data.files}
    saved = list(zip(raw["side"].tolist(), raw["m"].tolist(), raw["n"].tolist(), raw["polarization"].tolist(), strict=True))
    if saved != [tuple(row) for row in keys] or not np.all(raw["trace"] == 1):
        raise ValueError("saved mode ordering or trace mismatch")
    x, y = raw["surface_x_axis_nm"], raw["surface_y_axis_nm"]
    nx, ny = len(x)-1, len(y)-1
    i, j = map(int, raw["representative_face_indices"][0])
    if (nx, ny, i, j) != (272, 4, 100, 1):
        raise ValueError("saved face partition changed")
    x0, dx = float(x[i]), float(x[i+1]-x[i])
    y0, dy = float(y[j]), float(y[j+1]-y[j])
    element = basix.ufl.element("N1curl", "hexahedron", 6).basix_element
    p = int(element.degree)
    q, _ = np.polynomial.legendre.leggauss(p+1)
    q = (q+1)/2
    v = np.polynomial.legendre.legvander(2*q-1, p)
    gx, gy = np.meshgrid(q, q, indexing="ij")
    face_coeff, map_records = {}, []
    for side in ("bottom", "top"):
        active, rows, weights = face_map(element, side, i, j, nx, ny, raw["floquet_phases"], len(raw["trace"]))
        zref = 0. if side == "bottom" else 1.
        pts = np.column_stack((gx.ravel(), gy.ravel(), np.full(gx.size, zref)))
        tab = element.tabulate(0, pts)[0][:,:,:2].reshape(p+1,p+1,element.dim,2)
        c1 = np.linalg.solve(v, tab.reshape(p+1,-1)).reshape(tab.shape)
        coeff = np.linalg.solve(v, c1.swapaxes(0,1).reshape(p+1,-1)).reshape(tab.shape).swapaxes(0,1)
        local = raw["trace"][rows] * weights
        if not np.all(local == 1) or not np.all(weights == 1):
            raise ValueError("selected internal face unexpectedly wraps a Floquet edge")
        face_coeff[side] = np.einsum("abdc,d->abc", coeff[:,:,active,:], local, optimize=True)
        map_records.extend([[side,int(d),int(r),float(w.real),float(w.imag)] for d,r,w in zip(active,rows,weights,strict=True)])
    map_hash = hashlib.sha256(json.dumps(map_records,separators=(",",":")).encode()).hexdigest()
    mx_cache, my_cache = {}, {}
    reference = np.empty((len(modes),2), dtype=np.complex128)
    for idx, row in enumerate(modes):
        kv = tuple(z(v) for v in row["k_vector"])
        if kv[0] not in mx_cache:
            mm = legendre_exponential_moments(-kv[0].conjugate(),x0,dx,p,dps=80)
            mx_cache[kv[0]] = np.asarray([complex(vv) for vv in mm])
        if kv[1] not in my_cache:
            mm = legendre_exponential_moments(-kv[1].conjugate(),y0,dy,p,dps=80)
            my_cache[kv[1]] = np.asarray([complex(vv) for vv in mm])
        zplane = -10. if row["side"] == "bottom" else 130.
        phase = np.exp(-1j*kv[2].conjugate()*zplane)
        integ = np.einsum("a,b,abc->c",mx_cache[kv[0]],my_cache[kv[1]],face_coeff[row["side"]],optimize=True)
        reference[idx] = phase*integ*np.asarray([dy,dx])
    e = np.asarray([[z(v) for v in row["e_vector"][:2]] for row in modes],dtype=np.complex128)
    h = np.asarray(raw["denominators"],dtype=np.float64)
    ref_recover = np.sum(e.conj()*reference,axis=1)/h
    scale = np.maximum(np.linalg.norm(raw["q60_components"],axis=1)/np.abs(h),np.finfo(float).tiny)
    err60 = np.abs(raw["q60_recover"]-ref_recover)/scale
    rec30 = np.sum(e.conj()*raw["q30_components"],axis=1)/h
    err30 = np.abs(rec30-ref_recover)/scale
    comp60 = np.linalg.norm(raw["q60_components"]-reference,axis=1)/np.abs(h)
    worst = int(np.argmax(err60))
    def key(idx):
        r=modes[idx]
        return [r["side"],r["m"],r["n"],r["polarization"]]
    fixed=8576
    row=modes[fixed]
    kv=tuple(z(v) for v in row["k_vector"])
    zplane=-10. if row["side"]=="bottom" else 130.
    def fixed_projection(dps):
        ax=legendre_exponential_moments(-kv[0].conjugate(),x0,dx,p,dps=dps)
        ay=legendre_exponential_moments(-kv[1].conjugate(),y0,dy,p,dps=dps)
        ctx=mp.mp.clone(); ctx.dps=dps
        phase=ctx.exp(-ctx.j*ctx.conj(ctx.mpc(kv[2].real,kv[2].imag))*ctx.mpf(zplane))
        out=[]
        for c,scale_c in enumerate((dy,dx)):
            total=ctx.mpc(0)
            for a in range(p+1):
                for b in range(p+1):
                    c0=face_coeff[row["side"]][a,b,c]
                    coef=ctx.mpc(float(c0.real),float(c0.imag))
                    total += ctx.mpc(ax[a])*ctx.mpc(ay[b])*coef
            out.append(phase*total*ctx.mpf(scale_c))
        return tuple(out)
    with mp.workdps(110):
        ref80,ref100=fixed_projection(80),fixed_projection(100)
        d100=max(abs(a-b) for a,b in zip(ref80,ref100,strict=True))
        r100=d100/max(mp.mpf(1),max(abs(v) for v in ref100))
    report={
        "schema":"task40extra.w1_independent_mpmath_saved_array_attribution.v1",
        "status":"PASS_Q60_REFERENCE_GATE" if float(err60.max())<=1e-10 else "Q60_REFERENCE_GATE_FAIL",
        "source_head":"c354afa449fb80cfb5012e7d2ff66a3e3e64e088",
        "raw_npz_sha256":RAW_SHA,"mode_manifest_sha256":MANIFEST_SHA,"ordered_key_sha256":key_hash,
        "mode_count":len(modes),"moment_precision_dps":80,
        "moment_cache_counts":{"x":len(mx_cache),"y":len(my_cache)},
        "selected_face":{"i":i,"j":j,"x0":x0,"dx":dx,"y0":y0,"dy":dy},
        "independent_face_mapping_sha256":map_hash,"mapping_rows":len(map_records),
        "basix_polynomial_family":"N1curl/hexahedron/p6; rebuilt from Basix tabulation",
        "original_H_preserved":True,
        "q60_scale":"norm(saved q60 component vector)/abs(original H)",
        "q60_reference_gate":{
            "threshold":1e-10,"max_relative_recovered_error":float(err60.max()),
            "max_component_delta_over_H":float(comp60.max()),"worst_mode_index":worst,
            "worst_key":[modes[worst]["side"],modes[worst]["m"],modes[worst]["n"],modes[worst]["polarization"]],
            "pass":bool(err60.max()<=1e-10)},
        "q30_reference_diagnostic":{
            "max_relative_recovered_error":float(err30.max()),
            "worst_mode_index":int(np.argmax(err30)),
            "worst_key":[modes[int(np.argmax(err30))]["side"],modes[int(np.argmax(err30))]["m"],modes[int(np.argmax(err30))]["n"],modes[int(np.argmax(err30))]["polarization"]]},
        "fixed_100_digit_check":{
            "mode_index":fixed,"key":[row["side"],row["m"],row["n"],row["polarization"]],
            "precision_pair":[80,100],"relative_difference":mp.nstr(r100,12),"pass":bool(r100<=mp.mpf("1e-70"))},
        "old_negative_preserved":{"q30_q60_max_relative":5.705909332721303,
            "worst_mode_index":8576,"worst_key":["top",-67,-34,"s"],
            "raw_rewritten":False,"production_runner_rerun":False}}
    out=ART/"w1_mpmath_saved_attribution_v1.json"
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps(report,indent=2,sort_keys=True))

if __name__ == "__main__":
    main()
