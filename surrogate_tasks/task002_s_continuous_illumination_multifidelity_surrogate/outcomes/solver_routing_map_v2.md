# Task002 solver routing map v2

| Route | Status | Permitted role |
|---|---|---|
| Full3D static uniform N1curl p5/h10 | qualified operational HF | sole production-surrogate candidate pending Review V4 |
| Full3D static uniform N1curl p4/h10 | solver qualified, fidelity relation rejected | diagnostics and paired fidelity studies only |
| Full3D static uniform N1curl p4/h7.5 | not LF | independent discretization-error validation only |
| Hybrid p4/p6 M120 | hard quarantined | research diagnostics only; cannot enter Task002 formal campaign or dataset |

The production registry accepts only the p4/h10 and p5/h10 Full3D model IDs.
Hybrid IDs fail closed in the Task002 schema and campaign CLI. The p4 candidate
does not pass the complete multifidelity value Gate, so the effective production
surrogate route is p5-only. M3 remains closed pending Review V4.

All p5 predictions must carry discretization uncertainty. Neither p5/h10 nor
p4/h7.5 is described as continuum truth.
