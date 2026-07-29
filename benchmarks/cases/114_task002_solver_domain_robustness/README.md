# Case114: Task002 M2B solver-domain robustness

This case qualifies solver routes at the fixed center geometry only. It is not a
surrogate dataset and does not modify Case112/113 evidence or the formal 49-point
campaign manifest. All existing numerical gates remain unchanged.

Formal PDE source: `673c66ddee116e683a21b7ea8a90dc158cac2069`.

The case contains seven tracked compact records. Rebuild and verify them with:

```bash
source scripts/activate_myfenics_surrogate_wsl.sh
python -m benchmarks.check_case114_task002_m2b \
  --artifact-root benchmarks/artifacts/cases/114/m2b \
  --check-records
```

The independent reference set includes p3/p4/p5 at A--D and the Review-V2
authorized p4/h7.5 refinement. The latter follows the p5 response branch. The
final disposition is a controlled negative qualification: Hybrid remains paused,
Route 4 is selected, and M3 remains closed pending Review V3.
