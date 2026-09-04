# V17 Oracle B：unrestarted disk-backed Krylov

## 结论

Oracle B compares two methods from the same p6/h10 checkpoint and the same RHS/initial solution. The reference is right GMRES with restart 20; the candidate is one unrestarted right flexible GMRES sequence whose Arnoldi vectors are written to disk. The test asks whether long-memory Krylov information helps the fixed physical operator; it is not a full PDE recovery and it does not change the PC or physics.

The evidence is valid: `checker_recheck_v2.json` has `status=PASS`, `evidence_valid=true`, `errors=[]`, and no evidence Gate failures. The mechanism result is `UNRESTARTED_KRYLOV_WEAK_SIGNAL`: at step 500, `r_unrestarted/r_GMRES20=0.4006010510326989`, which is better than the restarted reference but not the frozen `<=0.1` strong-signal threshold.

## Same-start authority and settings

Both methods use iteration-1000 checkpoint, stored explicit true residual `0.4837947981092168`, checkpoint manifest `7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139`, solution SHA `00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b`, and the same physical operator. The raw RHS array has SHA `e8ece14d273d8bcdec672f2e29ac8c62971bb0d0fe4af7cc63e741df21934686`, and the initial solution array has SHA `7567b3d23892a82dfddb548a9727a936f2c90eb79effbe01c3a7e282c0527a6f`; both methods report their borrowed inputs unchanged and finite. Their initial explicit true residuals are `0.48379479479924` and `0.4837947947992396`.

| method | fixed settings | measured final |
|---|---|---:|
| reference | right GMRES; restart `20`; start `1000`; exactly `500` additional iterations; cycle max `20`; residual replacement true; unpreconditioned norm | `0.48362582271206495` |
| unrestarted | right FGMRES; one unrestarted sequence; `500` steps; no restart/residual replacement; disk V/Z; unpreconditioned norm | `0.19374101288500692` |

The reference used 25 cycles from 1000 through 1500. Every cycle has 20 iterations, 21 MatMults and 21 right-PC applies: the additional final-solution apply is part of the actual PETSc lifecycle. Totals are iterations `500`, matvec `525`, PC `525`, explicit actions `26`, observer packets `25`, KSP destroys `25`. The unrestarted totals are actions `526 = 1 + 500 + 25`, PC `500`, explicit packets `25`, and 500 iterations.

## Explicit true-residual curves

Values below are the complete raw 20-step history. `r_GMRES20` is the restarted reference; `r_unrestarted` is the disk-backed method.

| step | r_GMRES20 | r_unrestarted |
|---:|---:|---:|
| 20 | 0.48368937157782677 | 0.4836893715778267 |
| 40 | 0.4836813842600978 | 0.41511808143440193 |
| 60 | 0.48367622417014716 | 0.3931750387473136 |
| 80 | 0.4836725789830693 | 0.3616380194612084 |
| 100 | 0.4836694367974149 | 0.3420598549905346 |
| 120 | 0.483666651694168 | 0.32781709555378535 |
| 140 | 0.4836643459506337 | 0.30898274511997176 |
| 160 | 0.4836622197792488 | 0.30005819645937243 |
| 180 | 0.4836603497237412 | 0.2906996597056122 |
| 200 | 0.483658559355917 | 0.2791600059722106 |
| 220 | 0.4836568629618107 | 0.27159840742240166 |
| 240 | 0.483655176848439 | 0.2646996728095746 |
| 260 | 0.4836534319849224 | 0.2574217505905769 |
| 280 | 0.4836515422973992 | 0.25121941431759864 |
| 300 | 0.4836493729441614 | 0.24472773364823097 |
| 320 | 0.48364684309915484 | 0.2383262801863158 |
| 340 | 0.4836439643879253 | 0.23237020422920443 |
| 360 | 0.4836408270611947 | 0.22671504586979982 |
| 380 | 0.4836377828197875 | 0.2210735702371039 |
| 400 | 0.4836350713244178 | 0.21691619628881942 |
| 420 | 0.4836327462687707 | 0.21093456451094383 |
| 440 | 0.4836307268387269 | 0.20664056424696137 |
| 460 | 0.48362894063258866 | 0.20094689802792484 |
| 480 | 0.48362733017831316 | 0.1975611739940664 |
| 500 | 0.48362582271206495 | 0.19374101288500692 |

At 300 and 500, the unrestarted residuals are `0.24472773364823097` and `0.19374101288500692`; their last-200 ratio is `0.7916594085878643`, with `last_200_descent=true`. This trend is diagnostic only and does not replace the strong/weak/no-signal thresholds.

## Disk basis, arithmetic, and resources

The unrestarted Arnoldi basis is genuinely disk-backed: `basis_in_memory=false`, `mmap=false`, with positional `V.bin` and `Z.bin` files. `H.npy` is the small Hessenberg matrix and is allowed in RAM.

| object | measured fact |
|---|---|
| `H.npy` | dtype `complex128`, shape `[501,500]`, bytes `4,008,128`, SHA `0a0b2ee6604d228697a42a22f8e135164282d492d43156decc5d9bf0c03e40ef` |
| `V.bin` | 500 written columns; 501-column capacity; 1,393,196,832 bytes; column bytes `2,780,832`; SHA `b9811694637d8449dcfd6bf3069cd781be469a30042c844566662154589c91c1` |
| `Z.bin` | 500 written columns; 1,390,416,000 bytes; column bytes `2,780,832`; SHA `d8869dccdb215e89a80dc89017f658013e47382a964fc8b284536abf2dffdab6` |
| basis manifest | bytes `127,042`; SHA `07c80a5dfee44eda0767448fe4787825385f6ecffa6208003c80ef9a8c4c51ff` |
| fsync/sync evidence | 25 recorded sync columns, exactly `[20,40,...,500]`; no larger fsync count is inferred |
| scratch | `2,783,612,832 B`; free disk before run `912,038,133,760 B` |
| vector window | persistent full-vector count `7`; bounded algorithmic window count `8`, bytes `22,246,656`; callback output is included in that bound |

The two-pass modified Gram–Schmidt orthogonality defect is `1.1527483430591924e-14`; every explicit-vs-Arnoldi closure is within `1.302575839369706e-14`; Hessenberg values are finite. These are measured arithmetic checks, not claims that every internal PETSc work array is bounded by eight vectors: the complete process is governed by the RSS measurement.

## Lifecycle, provenance, and historical checker record

Marker order is exactly `paths_ready → abi_ready → reference_complete → unrestarted_complete → record_written → release_complete`. The parent and worker exited naturally; all status values were readable and swap was zero. Parent process-tree peak RSS was `1,451,954,176 B`; worker-stage peak was `880,951,296 B`. PSS was not recorded in this raw B packet. Parent warning was `1,800,000,000 B`, hard/watchdog `2,000,000,000 B`; warning was not reached.

| file | SHA256 |
|---|---|
| [`B artifact root`](../../../benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/v17_oracle_b_v2/3e3ad22944333439e9f4a5d71abc4c7384855dff/mpi1) `parent_record.json` | `22f7a2e6f7428a66d0a1a7233c4e59694df3904105347b096b6e103b946b4d85` |
| `raw/B_record.json` | `bfd1bb9d8a74ff9d7f6c93c815b363e973e176d15911414f738e28f23fd64dad` |
| `marker_manifest.json` | `19c738b365f9aa12fa30d8afc001c291e020f1be20c235486024ae29c05d7a09` |
| `raw/unrestarted/basis_manifest.json` | `07c80a5dfee44eda0767448fe4787825385f6ecffa6208003c80ef9a8c4c51ff` |
| original `checker.json` (unchanged historical record) | `6645aed16a60635d761612dfc363d6156511b8dccf3381cadbeafc26a826421f` |
| `checker_recheck_v2.json` | `c2c5e22a198c28654fcfb6177b1ba678c7f060ebac0fafc122a42333fc5e2a41` |

The original checker’s PC-ledger assumption was an infrastructure defect; it remains immutable and is not reclassified. The later checker-only recheck reads the same raw records and accepts the actual 21 PC applies per restart cycle. The resulting WEAK signal is valid evidence, not a checker failure.

## Boundary

Oracle B does not authorize a 20,000-step physical PDE, recovery, R/T/A, a new PC family, or production adoption. Under the joint Review V17 rule, B is useful but not a strong-signal result.
