# Task003 M3S active-learning Round 1

This case is a design-bound plan for exactly eight new Ny4 p5 Full3D points.
The plan uses only the 96 training targets and input-side metadata for the
sealed validation and candidate pool. Run `python checker.py` before any FEM.

Formal points must use source SHA `10e3356ba8364286a452077f71d7e3b92ea24cd5`,
model `S_PROD_FULL3D_STATIC_P5_H10_NY4`, route
`full3d_static_uniform_n1curl_p5_h10_ny4`, mesh `(6,4,14)`, MPI2/thread1 and
the compact-surrogate output profile. Round 2/3, validation scoring and model
locking are not authorized by this case.
