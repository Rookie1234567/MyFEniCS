# Task007 M3 Level-A test summary

- frozen Task006 Legendre-3 oracle: loaded read-only
- off-grid targets: 12; contracts J1/J0; N1/N2 fixed noise realizations
- new FEM: 0
- Task006 model lock/data mutation: false
- sequential BO uses actual oracle query count and best evaluated point
- EI below `1e-3` switches to bounded local posterior-mean refinement; 473 switches were recorded
- Matern-5/2 ARD GP: 8 deterministic starts, training-only jitter selection `[1e-10,1e-8]`
- independent Case147 checker: `pass`, all 45,054 checks true, implementation source `555abf1`
- qualified Python compile: pass
