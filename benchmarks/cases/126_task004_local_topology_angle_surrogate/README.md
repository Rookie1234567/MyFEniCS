# Case126：Task004 M4E local/topology-aware qualification

Case126 is a training-only, response-blind qualification record.  It uses
the immutable Case125 `train96` package and compares only the finite M4E
candidate families required by Review V3.  The checker re-computes package
hashes, array identities, window support, and the two qualification contracts
without running a solver or importing the model-fitting implementation.

No new FEM, blind-validation response, Task003 frozen validation response,
model-selection lock, or second active-learning round is part of this case.
