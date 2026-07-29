# M3R p5 single-fidelity design freeze

## Decision

Task002 production is frozen to one route:

```text
S_PROD_FULL3D_STATIC_P5_H10
Full3D static uniform N1curl p5/h10/MPI2/thread1
```

`p4/h10`, `p4/h7.5` and all Hybrid identities are diagnostic-only. The
production parameter validator, campaign CLI and dataset writer fail closed for
all non-p5 routes. Dataset schema
`task002.s-p5-single-fidelity-dataset.v2` has only `train_indices.npy` and
`frozen_validation_indices.npy`; historical LF splits have no production
meaning.

## Frozen designs

All tables bind clean implementation SHA
`eaf17cd01f9e69eff4575b83ea94490a453e09bb`.

| Design | Count | Seed | Production use |
|---|---:|---:|---|
| initial p5 training | 96 | 20260729 | future M4 only |
| frozen p5 validation | 16 | 20260730 | final validation only |
| candidate pool | 4096 | 20260731 | future acquisition pool |
| discretization audit | 8 | deterministic | diagnostic only |

Training–validation, training–candidate and validation–candidate exact tuple
intersections are all empty. Validation is prohibited from feature-map,
transform, kernel, hyperparameter, model and acquisition selection. The audit
table is separate; four audit candidates intentionally coincide with training
anchors but can never enter the production dataset as audit results.

Combined design hash:
`f072c0f3ac03cd97026a85338fd4a79e3cd498c492aea1e79dacbb009e22faa3`.

Feature maps A/B/C are recorded as training-only cross-validation candidates;
frozen validation was not used to choose among them.

## Case115 addendum

The earlier nine-angle interpolation pilot was not fully disjoint from the
80-angle map: 6/9 angles intersect and only the three `grazing=5.25°` angles are
off-grid. It is therefore a qualification diagnostic, not formal frozen
validation. The original Case115 record and raw evidence remain unchanged.

## Scope stop

No M4 p5 bulk sample, surrogate fit, angle DOE or inversion was started.
