# Case111: Task001 illumination robustness diagnostic checkpoint

This case records the Task001 M9 investigation of the five failed illumination
configurations F1--F5.  It is a **controlled-stop checkpoint**, not a claim that
all five configurations have passed the formal qualification gates.

The investigation repaired F1's reciprocal trace-coordinate instability and
added diagnostics for coefficient degree, surface quadrature, exact variational
conormal duals, propagation/traction/reconstruction beta identity, modal-rank
convergence, interface placement, and middle-domain Poynting balance.  Independent
global p4/h10 Full3D references close energy for F2--F5, so the illumination
configurations are physically well posed.  The Hybrid P path still fails the
unchanged interface/energy gates and remains unqualified.

No Case110 passing record was changed or rerun.  No Task002 dataset generation,
surrogate training, or inversion was started.  Raw diagnostic artifacts remain
under `benchmarks/artifacts/cases/111/`; the tracked records here are compact
summaries bound to their artifact identifiers and implementation SHAs.

Run the commands in `test_command.txt` to check the non-PDE regression surface and
JSON records.  They do not launch the FEM campaign.
