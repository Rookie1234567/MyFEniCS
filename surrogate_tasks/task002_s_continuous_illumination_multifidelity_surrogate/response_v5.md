# Task002 Review V4 response (V5)

Required M3R is complete. M4, formal p5 bulk generation, surrogate fitting,
angle DOE and inversion were not started.

## Resolution of required items

1. Observable `task002.fixed-n0-orders.v3` freezes `n=0, m=-7..+3`, including
   explicit `m=+2,+3` identities. All 206 Case114/115 raw order artifacts were
   re-extracted and passed without PDE reruns.
2. Actual runtime mesh, cell/facet tags, Floquet objects and p5 function space
   are read from solved runtime objects and compared with an independently
   constructed plan. Five p5 smoke solves pass all identity and numerical Gates.
3. Parameter schema, campaign v2 and dataset v2 are p5-only:
   Full3D static uniform N1curl p5/h10/MPI2.
4. p4/h10, p4/h7.5 and all Hybrid routes are diagnostic-only and rejected from
   production campaign/dataset paths.
5. Case115's false fully-disjoint statement is corrected by a tracked addendum:
   6/9 pilot angles intersect the 80-angle map; the original evidence is not
   rewritten.
6. Frozen designs contain 96 training, 16 independent validation, 4096
   candidate and 8 discretization-audit points. Production splits are exact-
   tuple disjoint and hash-bound.
7. Every formal smoke and design binds clean implementation SHA
   `eaf17cd01f9e69eff4575b83ea94490a453e09bb`.

## Verification

- Case116 checker: 5/5 record Gate groups passed.
- Raw observable v3 audit: 206/206 re-extractions passed.
- Runtime qualification: 5/5 measured_pass, zero swap, complete cleanup.
- Task002 focused tests: 33 passed.
- Final full repository suite: 681 passed, 28 skipped, 7 failed. The stale
  numbered-case registry (which already missed Cases110–115) was repaired with
  a dedicated surrogate-case contract for Cases110–116. The remaining failures
  are existing environment/history authorities: unreadable/zero WSL cgroup
  memory metadata, shallow-clone-missing Task033 history objects and the
  existing Task034 numerical-change classification gap.
- Python compile checks and `git diff --check` passed.

## Stop state

```text
production_route = Full3D_p5_h10_single_fidelity
observable_schema = task002.fixed-n0-orders.v3
M3R = complete
M4 = not_authorized
next_action = stop_and_wait_for_Review_V5
```
