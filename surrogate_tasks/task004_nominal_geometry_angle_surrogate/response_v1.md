# Task004 response V1

Task004 M0 design and implementation work reached a controlled stop during
the required new clean-SHA forward qualification. The baseline is
`7fe366304023c32bf2e8ddcacdb2ada9996d3e7c`; five fixed-geometry anchors were
required, but the first point `(grazing=0.5°, azimuth=0°)` failed at MUMPS
direct-LU factorization (`INFOG(1)=-9`, `INFO(2)=919260`) before residual,
energy, or observable records could be produced. Swap remained zero and the
failure was preserved without retrying or skipping the point.

The independent 96-training, 24-blind-validation and 4096-candidate angle
designs are frozen and response-blind. The finite angle-model candidates and
`AngleSurrogate.predict(grazing_deg, azimuth_deg)` implementation are present,
but no model was trained or locked. No Task004 training/validation FEM, active
learning, dense maps, Fisher ranking, geometry sensitivity, inversion, P
polarization, wavelength extension, Task003 Round3, or Task003 validation
access was performed.

This response stops for review at the first unexplained numerical failure.
