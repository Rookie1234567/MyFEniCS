# Task004 angle design

All designs are fixed at `height_nm=120`, `width_x_nm=17`, wavelength 13.5 nm,
S polarization, and bind clean SHA
`7fe366304023c32bf2e8ddcacdb2ada9996d3e7c`.

| design | count | tuple hash | use |
|---|---:|---|---|
| structured training + enrichment | 96 | `bfd68a374e5510284a972c640c6332d818917052ae30bd77c10af5240f0500ef` | not measured |
| independent blind validation | 24 | `af6cc7c87236aa2e1050b40f1cca1282932e071b22b3b767057b94bc8c11af57` | sealed, not measured |
| candidate pool | 4096 | `db2a6155274614b5129846ace0a277fe69161f2e5120966d7968d6b210d981fa` | response-blind |
| clean-SHA anchors | 5 | `63decea83a844d49a9e6a49e0ca01dddf548b8e2e592eea1b3bfadfaf8ec63f5` | stopped at first failure |

Training and validation have zero exact tuple intersection. The enrichment
selection uses only Sobol coordinates, analytic signed cutoff margins, low-
grazing labels and maximin distance; it reads no response arrays.
