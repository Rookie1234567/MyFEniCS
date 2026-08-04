# Task005 Fisher DOE ranking

The Fisher calculation uses the frozen central-difference Jacobians from the
16-angle compact dataset.  `M0` contains only `[R_total,T_total]`; `M1` and
`M2` contain active fixed-order total powers at thresholds `1e-3` and `1e-5`.
Thus no absorption, aggregate/order duplicate, amplitude, phase, or ratio is
counted twice.  N1 and N2 are provisional diagonal noise scenarios, not an
experimental covariance calibration.

All combinations were enumerated exactly: 16 singles, 120 pairs, 560
triples, and 1820 quadruples.  2513 combinations are full rank for both M0
and M1 under both N1 and N2.

| size | best combination | worst-case minimum eigenvalue | worst-case logdet | worst-case condition |
|---:|---|---:|---:|---:|
| 1 | A05 | 12.882983 | 6.726299 | 5.2336859 |
| 2 | A05 + A07 | 23.781704 | 8.055676 | 5.7495725 |
| 3 | A05 + A07 + A09 | 34.768648 | 8.553123 | 4.2874404 |
| 4 | A05 + A06 + A07 + A09 | 45.149335 | 9.195723 | 4.8344722 |

The frozen robust recommendation is the three-angle set:

```text
A05 = (2°, 0°)
A07 = (2°, 90°)
A09 = (4°, 60°)
```

The ranking is a local design metric around `(h,w)=(120,17) nm`; it is not a
claim that the Fisher CRLB is an achieved metrology uncertainty and it is not
a Bayesian inversion.
