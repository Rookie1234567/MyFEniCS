# Case117 — Task002 p5 production campaign

Case117 is the evidence authority for Review V5 M4P and M4. It hardens the
design-bound resume-safe campaign, qualifies compact output, then records the
frozen 96-point training and 16-point frozen-validation p5 datasets.

The only production solver is Full3D static uniform N1curl p5/h10 with
MPI2/thread1. Every production sample must belong to a rebound Case116 frozen
design and pass residual, energy, observable-v3, runtime-topology,
`n!=0`-leakage, power-ledger, zero-swap, cleanup and compact-output Gates.

M4 generates and seals data only. PCE/GP fitting, validation evaluation,
feature selection, active learning, angle DOE and inversion remain forbidden.

Records are generated incrementally after the clean M4 implementation baseline:
preflight/leakage/compact-equivalence/design-rebind first, then canary,
training, validation, dataset and resource summaries. The command in
`test_command.txt` verifies the final compact evidence without running PDE.
