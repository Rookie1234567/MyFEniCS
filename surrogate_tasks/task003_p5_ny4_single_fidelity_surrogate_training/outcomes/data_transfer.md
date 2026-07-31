# Data transfer and local execution

The Review V8 local CPU addendum overrides workstation transfer for Task003.
No `scp`, `rsync`, or binary package copy was performed. The immutable compact
dataset was verified in place against its tracked manifest and all ten file
hashes. The FEM `.venv` fingerprint was recorded and not modified; the new
`.venv-surrogate-cpu` contains NumPy/SciPy/scikit-learn/psutil only and no
CUDA dependency.

