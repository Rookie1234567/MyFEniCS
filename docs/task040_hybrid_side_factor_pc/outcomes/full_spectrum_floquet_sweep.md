# Full-spectrum Floquet sweep outcome

## 结论边界

全频谱路线先把 H(curl) trace 的 canonical channel 映射到完整的 15×7 harmonic 网格，再做
Floquet/FFT 传播，避免把 PETSc raw row 顺序误当空间顺序。tiny serial/MPI2 regression 通过
canonical block、phase-once、FFT/DFT、coverage 和 dual pairing；MPI8 formal 没有形成可审计
sweep 数值，因此本页不是 `FULL_SPECTRUM_SWEEP_NO_SIGNAL`。

## 实际历程

### 第一次 MPI8 root：几何 extent 假设

root：
`/home/fenics/Projects/MyFEniCS/results/task040_v7_scale_normalized_identity_mpi8_e7fee3c2_native`。
实际命令为：

```text
python -m benchmarks.task040_level_a_watchdog --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v7_scale_normalized_identity_mpi8_e7fee3c2_native --source-sha e7fee3c2f7af8110698276a1789c8435fbc5db48 --v7-scale-normalized-identity --watchdog-enabled --bottom-route-only
```

该命令由 watchdog 以 MPI8/threads1 worker 执行，资源配置为 45 GiB、21600 s。

scale identity raw/checker 在该 root 已完成并给出 D0/D1 candidate；随后 continuation 抛出：

```text
ValueError: full-spectrum metadata failed: Gamma entity extent is not one periodic cell
```

根因是第一版 trace metadata 以浮点 uniform step 解释实际 entity geometry，而不是使用离散
canonical point-level inventory；watchdog `natural_exit`、worker return `1`，elapsed
`773.3814081490054 s`，peak RSS `36689285120 B`，swap `0`，authoritative samples `1329`，
没有 run summary。关键 SHA：watchdog
`0f64f8daf23ae1644c90b390c4b3d83fe60dc51cc3c258eae7cb9cab7824fbbc`，worker stdout
`c065334908ed21a46c6ba9c0848255bca4a96f70d71b02dde0d0ccac90358659`，markers
`fe3314aa5390ef058f6242c4571ddd60cfed96b2c2f800726cd7879e00ac5233`。

### 量化 level 修复后的 root：empty-local probe divergence

root：
`/home/fenics/Projects/MyFEniCS/results/task040_v7_scale_normalized_identity_mpi8_ab51cad1_native`，
source SHA=`ab51cad19f25b1853d0b9ed479a3350dfdf24f4b`。实际命令为：

```text
python -m benchmarks.task040_level_a_watchdog --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v7_scale_normalized_identity_mpi8_ab51cad1_native --source-sha ab51cad19f25b1853d0b9ed479a3350dfdf24f4b --v7-scale-normalized-identity --watchdog-enabled --bottom-route-only
```

x/y 坐标改为离散 level inventory 后，
formal 在 `_canonical_probe` 抛出：

```text
ValueError: canonical full-spectrum probe is invalid
```

部分 rank 合法持有 empty local rows，却被 rank-local 判为 invalid；其他 rank 继续 collective，
形成 rank divergence。该 root 没有 watchdog summary；worker stdout SHA
`af84db4a21b49f8bd5353596d9bb152a95a262459cfda835d67e9b265543f634`，markers SHA
`902b10a0319e84fd2ef751dce0f3003885a0da0d9dc79a313be8e658d605c9c7`，stages SHA
`20731b117a7b95affb324733dc4cb92821ef08086ba90e633e0312bf20c5c13f`。

随后 `a2acb934` 仅将 empty-local 情形改成 collective-safe 判定：所有 rank 对 finite 用
LAND、对“至少一个非零 local payload”用 LOR，再统一继续或统一失败；serial/MPI2 targeted
regression 通过。按 Review 的 corrected formal 额度和“不得第三跑”纪律，没有把 targeted
修复夸大成 MPI8 formal pass。

## 当前状态与关闭理由

没有 Floquet symbol、105 harmonic screen、r8/r16/r32/r64、two-source signal 或 physical
DtN 数值结论。full-spectrum route 的关闭理由是 formal 证据在 metadata/probe 实现层未闭合，
且后续 moving-PML 已达到真实 wall/resource stop；不是已证明 full-spectrum 数值无信号，也
不是 0.7 nm 不可行。旧 V6-2 absolute negative 保持独立有效，见
[full-interface identity](full_interface_schur_identity.md)。
