# Case119 — Task002 p5/Ny4 production campaign

Case119 is the isolated Review V7 M4E authority. It corrects the diagnostic
projection to the tangential trace contract, hard-freezes the only production
route as Full3D static uniform N1curl p5/h10 with `(Nx,Ny,Nz)=(6,4,14)`, runs
the enhanced canary, and—only after that Gate passes—generates a fresh 96+16
Ny4 dataset.

Case117 remains immutable controlled-stop evidence. No Ny3 sample is eligible
for this campaign or dataset.

Final status: the enhanced canary passed, all 96 training and 16 frozen
validation samples are measured-pass, and the independent exact-design dataset
checker passes. The frozen validation responses remain sealed from model
selection. Run the tracked evidence checker with:

```bash
python -m benchmarks.check_case119_task002_m4e --verify
```
