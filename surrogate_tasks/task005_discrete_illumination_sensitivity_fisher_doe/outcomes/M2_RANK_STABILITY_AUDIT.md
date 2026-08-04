# M2 ranking stability audit

This report is derived only from the immutable v1 Fisher tables and raw sensitivity package. No FEM was run.

| size | robust best | M2/N1 best | M2/N2 best | M2 worst-case best | selected set M2 worst rank |
|---:|---|---|---|---|---:|
| 1 | `['A05']` | `['A05']` | `['A05']` | `['A05']` | 1 |
| 2 | `['A05', 'A07']` | `['A05', 'A09']` | `['A05', 'A07']` | `['A05', 'A07']` | 1 |
| 3 | `['A05', 'A07', 'A09']` | `['A05', 'A09', 'A11']` | `['A05', 'A07', 'A09']` | `['A05', 'A07', 'A09']` | 1 |
| 4 | `['A05', 'A06', 'A07', 'A09']` | `['A05', 'A07', 'A08', 'A09']` | `['A05', 'A06', 'A07', 'A09']` | `['A05', 'A06', 'A07', 'A09']` | 1 |

The M2-only diagnostic contains **28** weak-channel observations across **13** angles.
Their nominal powers range from `1.27707e-05` to `0.000818441`; N1 sigma ranges from `0.0001` to `0.000100334`, and N2 sigma from `0.0005` to `0.000500268`.

Worst-case M2 (N1/N2) preserves the robust selected single, pair, triple and quad at rank 1. Isolated M2/N1 can choose A05+A09, A05+A09+A11, or A05+A07+A08+A09 because near-floor channels receive an N1-only influence; this is explicitly diagnostic and does not change the robust lock.

| size | common full-rank count | top-10 overlap | top-20 overlap | Spearman |
|---:|---:|---:|---:|---:|
| 1 | 13 | 10/10 | 13/13 | 1.000000 |
| 2 | 120 | 10/10 | 20/20 | 0.999681 |
| 3 | 560 | 10/10 | 20/20 | 0.999902 |
| 4 | 1820 | 10/10 | 20/20 | 0.999940 |

Conclusion: M2 weak channels do not overturn the M0/M1 worst-case choice, but their N1-only best-set changes are recorded as a stability warning. M2 remains a diagnostic weak-channel contract.
