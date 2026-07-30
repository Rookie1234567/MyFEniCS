# Case116 — Task002 M3R p5-only design freeze

Case116 is the compact evidence authority for Review V4 M3R. It qualifies the
observable-v3 contract, independently checks actual runtime topology, freezes
the single-fidelity production interfaces and freezes future M4 designs. It is
not an M4 dataset and contains no surrogate fit or angle DOE result.

## Frozen production identity

```text
source SHA = ba50cd36b081637ed5ea97c2dc8e4827d992b940 (Review V5 metadata rebind)
solver = Full3D static uniform N1curl p5/h10/MPI2
observable = task002.fixed-n0-orders.v3, n=0, m=-7..+3
dataset = task002.s-p5-single-fidelity-dataset.v2
```

Full3D p4/h10, Full3D p4/h7.5 and every Hybrid identity are diagnostic-only.
Production parameter validation, campaign manifests and dataset assembly reject
them.

## Evidence

The five JSON records under `records/` cover:

- v3 re-extraction of 206 immutable Case114/115 raw order artifacts;
- five clean-SHA p5 smoke solves with actual mesh/tag/Floquet/function-space
  identity read from runtime objects;
- p5-only parameter, campaign and dataset contracts;
- exact design/split hashes;
- the Case115 false-disjoint validation addendum.

The four design tables contain 96 training points, 16 independent frozen
validation points, 4096 candidate points and 8 discretization-audit candidates.
They are design-only. No point in these files was executed as an M4 sample.
The Review V5 rebind changed source/combined metadata only; every tuple and the
four point-tuple hashes remain identical to the approved M3R tables.

## Reproduction and disposition

Activate the qualified WSL environment and run `test_command.txt`. All five
record Gate groups must pass. M4 remains closed pending Review V5.
