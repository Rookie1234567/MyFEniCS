# Task003 M3T fixed-reference audit and conditional Round 2

`checker.py` is an independent exact-design and M3T Gate checker. It must pass
before the optional Round-2 plan is accepted. The checker reads input tuples,
array headers and file hashes only; frozen-validation response arrays are not
loaded. Round 2 is exactly eight Ny4 p5 Full3D points and is forbidden unless
all Review V2 Section 6 conditions pass.

The production identity remains source SHA `10e3356ba8364286a452077f71d7e3b92ea24cd5`,
model `S_PROD_FULL3D_STATIC_P5_H10_NY4`, route
`full3d_static_uniform_n1curl_p5_h10_ny4`, mesh `(6,4,14)`, MPI2/thread1.
