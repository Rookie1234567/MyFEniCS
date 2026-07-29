# Case115 — Task002 Full3D hierarchy qualification

This case is the compact evidence authority for Review V3 Required M2C. It does
not open Task002 M3 and it is not a surrogate-training dataset.

## Qualified scope

- wavelength: 13.5 nm; S polarization only;
- geometry audit: height 115–125 nm and width 16–18 nm;
- angle domain: grazing 0.5–10°, azimuth 0–90°;
- LF candidate: Full3D static uniform N1curl p4/h10;
- operational HF: Full3D static uniform N1curl p5/h10;
- p4/h7.5: discretization-error audit only;
- Hybrid: hard-quarantined from Task002 production.

All new PDE runs are MPI2/thread1, one solve at a time, watchdog protected, and
bound to clean implementation SHA
`fe0e53571491f21e4774d7576d9285f9a09df705`.

## Evidence layout

The seven JSON files in `records/` contain the 80-angle p5 map, paired fidelity
screen, topology audit and real-run smoke, geometry sensitivity pilot,
discretization uncertainty, Hybrid quarantine evidence, and routing decision.
Case112–114 raw artifacts are referenced by hash and are not rewritten.

## Reproduction

Activate the qualified WSL environment and run the command in
`test_command.txt`. The checker regenerates compact records from immutable raw
artifacts and exits nonzero if an evidence-integrity Gate fails.

## Disposition

The p4→p5 hierarchy is not qualified for production multifidelity because the
absorption-channel Spearman correlation is below 0.90 and low-grazing geometry
sensitivity differs materially. The production surrogate route is therefore
frozen as Full3D p5 single fidelity pending Review V4. M3 remains closed.
