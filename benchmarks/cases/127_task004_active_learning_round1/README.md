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
