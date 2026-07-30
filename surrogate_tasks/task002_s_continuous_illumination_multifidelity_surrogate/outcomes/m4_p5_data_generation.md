# M4 p5 data generation — controlled stop

## M4P result

The design-bound campaign v3, p5 leakage/ledger Gates, compact output profile,
formal-record adapter and independent exact-design dataset checker were
implemented at clean SHA
`ba50cd36b081637ed5ea97c2dc8e4827d992b940`.

Historical p5 80-angle leakage authority supports the frozen thresholds:

```text
max n!=0 total power = 4.93664017988878e-09
max n!=0 amplitude   = 3.971065398159596e-05
production Gates     = 1e-7 and 1e-4
```

Two ordinary/compact A/B points passed structure-aware numerical comparison.
R/T/A/volume/closure differences were at most `1.066e-12`; mother-response
numeric differences were at most `4.989e-13`. Compact payload was about
0.62–0.66 MB versus about 14.4 MB ordinary, with no VTU/PVD/BP output.

The Case116 designs were metadata-rebound to the new SHA. All four tuple tables
and tuple hashes are unchanged.

## Canary and campaign progress

- 16/16 four-dimensional domain corners passed every Gate;
- three complete 16-point summaries passed (indices 64–79, 0–15, 16–31);
- 56 training points reached `measured_pass`;
- attempt wall range was 58.51–80.82 s;
- peak RSS range was 4.19–4.33 GB;
- every completed attempt had zero swap and complete cleanup.

## First failure and mandatory stop

The first failure occurred at training design index 40:

```text
(height_nm, width_x_nm, grazing_deg, azimuth_deg)
= (116.446369998157, 17.513626368716, 4.538499870338, 54.420819282532)

n!=0 reflection power = 1.2727992374361636e-07
n!=0 transmission power = 1.1039521076787467e-06
n!=0 total power = 1.231232031422363e-06
n!=0 max amplitude = 1.0146566168132453e-03
```

The dominant channel is bottom `(m=0,n=-3,S)`. Residual, energy closure,
fixed/raw ledger, actual topology, compact identity, zero-swap and cleanup all
passed. Only the two frozen leakage Gates failed. The campaign stopped
immediately after attempt 1; no retry or later-point execution occurred.

Final inventory: 56 passed, 1 failed, 39 training points not run. Frozen
validation was not started.
