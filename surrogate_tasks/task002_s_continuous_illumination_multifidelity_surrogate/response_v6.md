# Task002 Review V5 response (V6 controlled stop)

M4P completed, the 16-point canary passed, and M4 then stopped at the first
unexplained numerical production Gate failure exactly as required. M4 is not
complete. No failure was skipped, no threshold was changed and no retry was
performed.

## Completed engineering

1. Campaign v3 is design-bound, atomic and resume-safe, with attempt history,
   stale artifact recovery, retryable interruption state and first-failure stop.
2. p5-only `n!=0` authority, hard Gates and fixed/raw port ledger are enforced.
3. `compact_surrogate_record` preserves solve/DtN/volume/runtime identity while
   omitting field visualization output.
4. Two ordinary/compact A/B points passed within numerical tolerance.
5. The deterministic formal-record adapter and independent exact-design dataset
   checker are implemented and synthetic-tested.
6. Clean M4 implementation SHA is
   `ba50cd36b081637ed5ea97c2dc8e4827d992b940`.
7. Case116 tuple tables are unchanged and metadata-rebound to that SHA.

## Campaign result

```text
canary = 16/16 pass
training = 56 measured_pass, 1 failed, 39 not_run
frozen validation = 0 run
dataset = not built
first failure = training design index 40
```

At the failed point, `n!=0` total power was `1.231232031422363e-06` and maximum
amplitude was `1.0146566168132453e-03`, above the frozen `1e-7` and `1e-4`
Gates. All other numerical, topology, ledger, compact and resource Gates passed.
The dominant leakage identity was bottom `(m=0,n=-3,S)`.

## Verification and stop boundary

- controlled-stop checker: 8/8 Gate groups passed;
- focused M4P/documentation tests before campaign: 50 passed;
- full repository test before campaign: 684 passed, 28 skipped, 7 known
  environment/history failures unrelated to Task002;
- 57 attempted PDEs all completed with zero swap and cleanup complete;
- no PCE/GP training, validation evaluation, active learning, angle DOE or
  inversion was started.

Task002 now stops for Review V6 diagnosis of the geometry-dependent `n=-3`
leakage. Continuing M4 would violate Review V5.
