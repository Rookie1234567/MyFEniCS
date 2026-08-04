# Task001 baseline pair comparison

The historical baseline pair `(10°,0°)+(10°,90°)` is A14+A15.  It is retained
as a valid comparison, but its local two-parameter information is weak under
the frozen Task005 contracts:

| pair | robust pair rank | worst-case minimum eigenvalue | worst-case logdet | worst-case condition |
|---|---:|---:|---:|---:|
| A14 + A15 | 120 / 120 | 7.49727e-6 | -10.35712 | 565138.05 |
| recommended A05 + A07 | 1 / 120 | 23.781704 | 8.055676 | 5.7495725 |

The comparison uses the same M0/M1 contracts and N1/N2 scenarios for every
pair.  It is evidence for illumination selection only; no formal inversion
has been performed.
