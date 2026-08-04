# Case131 — Task005 M0 design and finite-difference step audit

This case owns the independent M0 checker and the M1 audit evidence.  M0
reads only the immutable Task004 `train112` package and verifies the frozen
16-angle design, perturbation states, source identities, and nominal reuse.
It launches no FEM and never reads a blind-validation response.

M1 is allowed only after the Case131 M0 checker passes.  Its maximum budget is
40 new Full3D p5/Ny4 records: five prescribed angles, coarse and half steps,
four one-parameter states per step.  The first unexplained numerical failure
is a controlled stop.
