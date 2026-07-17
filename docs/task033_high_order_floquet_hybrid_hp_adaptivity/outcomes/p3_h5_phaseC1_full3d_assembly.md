# Task033 p3/h5 Phase C1 full3D assembly calibration

## Outcome

Phase C1 assembly-only passed on clean source
`35fa6a0c454d96875f9865260b13d22b43d06838`. The target p3/h5 mesh,
Nédélec space, Floquet constraints, full operator and auxiliary Fourier-DtN
augmentation were assembled with MPI4. No symbolic analysis, numerical
factorization or solve was entered.

```text
assembly calibration = pass
review C0 after calibration = still fails
p3 full solve = not authorized by review V4
p3 full solve = separately authorized by the user's later controlled-swap policy
p4 = locked
```

The last two statements are deliberately kept separate. The user's resource
authorization permits a controlled experiment; it does not retroactively make
the review Gate pass.

## Exact matrix and constraints

| Item | Measured value |
|---|---:|
| p3 Nédélec DOFs | 145,863 |
| Floquet constraint rows / raw-map NNZ | 8,703 / 8,703 |
| Floquet total setup | 0.2362 s |
| base rows / assembled NNZ | 145,863 / 35,441,847 |
| DtN auxiliary DOFs | 80 |
| final rows / assembled NNZ | 145,943 / 35,566,727 |
| final AIJ payload estimate | 815.171 MiB |
| DtN assembly path total | 75.192 s |

PETSc reports `MatInfo.memory = 0` in this build, so it is recorded as
unavailable rather than silently replaced. The separate AIJ payload estimate
uses the project's declared complex-value, index and row-pointer accounting.

No dense Floquet boundary square, dense DtN auxiliary boundary block or
explicit \(C^H A C\) was formed. The sparse DtN coupling contains an estimated
124,880 nonzeros; its dense-boundary equivalent would have been 23,338,160
entries.

## External memory authority

The 0.25 s external sampler observed all four MPI ranks for 308 samples:

| Item | Measured value |
|---|---:|
| simultaneous worker RSS peak | 4,247.438 MiB |
| cgroup `memory.current` peak | 3,971.715 MiB |
| formal memory authority | 4.147888 GiB |
| cgroup swap peak | 0 |
| `pswpin` / `pswpout` delta | 0 / 0 |
| OOM / watchdog termination | false / false |

This 4.148 GiB result is an assembly peak, not a full direct-solve prediction.

## Recomputed C0

The old Case090 transfer predicted 34,085,833 assembled NNZ. The exact target
matrix has 35,566,727 NNZ, 4.34% more. Replacing only the calibrated row/NNZ
part of the reviewed formula gives:

| Chain | Center |
|---|---:|
| effective \(p/h\) RSS power law | 6.444557 GiB |
| exact assembly NNZ → p2 fill → factor payload → RSS | 15.870052 GiB |
| conservative upper | 19.044063 GiB |

The second chain predicts 545,297,854 factor nonzeros and 12.197023 GiB of
factor payload. Against the live limits (10.563174 GiB per center and
11.757272 GiB conservative upper), the review Gate still fails. This is not a
surprising contradiction: assembly-only removed uncertainty in the target
matrix size, but did not measure p3 MUMPS fill.

## Controlled continuation

Review V4 requires stopping here. The user subsequently granted a narrower,
higher-priority resource authorization: p3/h5 may be attempted with controlled
swap. The next run therefore remains explicitly classified as a user-authorized
experiment under:

```text
memory.max = 13 GiB
memory + swap hard container budget = 20 GiB
warning = 12 GiB
watchdog termination = 18.5 GiB combined memory+swap authority
```

If p3 uses any swap, or its measured in-memory authority is at least 10 GiB,
p4 remains locked. Even if both user thresholds pass, p4 still requires its
own trace prerequisite and candidate-specific assembly/C0 Gate.

The tracked compact record is
`benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage3_p3_h5/phaseC1_full3d_assembly_summary.json`.
Hash-bound raw evidence remains under the ignored
`benchmarks/artifacts/cases/091/task033_full3d/p3_h5_assembly-only_mpi4_20260717T070352Z/`
directory.
