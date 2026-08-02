# Case123 — Task004 fixed-geometry angle surrogate

This case freezes the independent Ny4/p5 angle designs for the nominal
geometry `(height_nm,width_x_nm)=(120,17)`. It uses the same qualified Full3D
solver route as Task002, but has a new Task004 dataset identity and never
imports Task003 samples or validation targets.

The five-anchor design is used only to qualify the clean implementation SHA.
The 96 training angles and 24 blind-validation angles are run through the
design-bound Task002 Full3D campaign runner. The 4096-point candidate pool is
response-blind and exists only for optional one-time active learning.
