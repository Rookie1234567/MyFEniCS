# Case118 — Task002 y-direction alias qualification

Case118 is the isolated Review V6 M4D authority. It diagnoses the Case117
training-index-40 `n=0`/`n=-3` coupling without modifying Case117 evidence,
the frozen four-tuples, or the production leakage Gates.

The case compares the failed and center geometries over the prescribed
50--58 degree azimuth stencil, refines `Ny=3/4/5/6`, changes only the DtN
surface quadrature, independently projects `E_total`, and measures the actual
trace-vector Gram overlap. Every solve is diagnostic-only and hash-bound.

Clean diagnostic baseline:

```text
0a53c42397a2e67f64e8f6dae2c680bfe3fe4b95
```

The result confirms a Ny=3 discrete Bragg/trace alias. At the original failed
point the total n-nonzero leakage is `1.2312320314e-6`; with only Ny changed to
4 it falls to `3.2783435750e-25`. The actual bottom-S trace-vector overlap
between n=0 and n=-3 falls from `0.3630216842` to `2.6829e-16`. Raising surface
quadrature from auto q21 through q47 leaves the Ny=3 leakage unchanged.

Route A (Ny=4) is therefore supported as the next production candidate, but
M4 remains stopped. The independent field projection also exposed a separate
outgoing-P auxiliary/direct mismatch, retained in
`records/auxiliary_vs_direct_projection.json` for Review V7 disposition.
