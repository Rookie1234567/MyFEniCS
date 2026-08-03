# Case127 — Task004 M4E2 response-blind round-1 plan

This case is the independent contract for Required M4E2.  It verifies the
geometry-supported interpolation windows, the training-only OOF error maps,
the finite acquisition audit, and the exactly-16-point response-blind plan.
The checker does not import the M4E2 implementation, read blind responses, or
run a forward solve.  A missing `records/` directory is an intentional
pre-FEM state; it is not evidence that the 16-point campaign has passed.

The fixed forward identity for the eventual M4F campaign is
`fdf961545f217d620e22800f2704ae9913a6d270`, Full3D static uniform N1curl
p5/Ny4, ICNTL(14)=40, MPI2 and one thread per rank.  The campaign is not
authorized by this case until every plan Gate is independently recomputed.

After the authorized campaign, `post_fem_checker.py` independently verifies all
16 compact records and the immutable `train112` package.  `train112_checker.py`
then re-hashes that package, recomputes the exact 96+16 tuple identity, and
checks the training-only 112-point CV report.  The pre-FEM `case127_check.json`
is intentionally retained as an immutable record and must not be rerun after
FEM; its `fem_started=false` field describes the earlier authorization state.
