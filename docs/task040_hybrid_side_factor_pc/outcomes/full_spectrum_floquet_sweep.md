# Full-spectrum Floquet sweep outcome

## 当前正式结果（取代下面的预运行快照）

本路线的作用是把有限元 trace 行转换到完整的 Floquet channel/harmonic 网格，再开始两源 screen。这个转换身份检查已通过；但两源在 owner-vector load 处遇到 live canonical tokens 与 persisted layout 不一致，故不能把实现层失败误写成数值 no-signal。

| 项目 | 当前事实 |
|---|---|
| root / source | `results/task040_v8_full_spectrum_mpi8_089bf8a1_native_phase_repair1` / `089bf8a10441b83c5d293a02d649670675b631ca` |
| classification | `FULL_SPECTRUM_IMPLEMENTATION_FAILURE` |
| transform | identity `PASS`；actual lower/upper=`7560+7560`，`72 channels × 105 harmonics`；`numeric_allgather=false`；`full_plane_numeric_replica=false` |
| watchdog | natural rc0；elapsed=`1533.1877332139993s`；peak=`38975795200 B`=`36.29903793334961 GiB`；swap=`0` |
| source/checkpoint | 两个 source entries/orchestration 已形成，但 owner-vector load 失败；无 source begin/end raw marker、无 one-apply/FGMRES checkpoint、r8/r16/r32/r64 未形成；apply-count字段=`0` |

正式用户入口（watchdog 内部 MPI8 命令由 summary 复核）：

```text
python -m benchmarks.task040_level_a_watchdog --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v8_full_spectrum_mpi8_089bf8a1_native_phase_repair1 --source-sha 089bf8a10441b83c5d293a02d649670675b631ca --v8-full-spectrum-only --watchdog-enabled --bottom-route-only
```

| raw marker | stage wall (s) | RSS (B) | swap | PC/action apply |
|---|---:|---:|---:|---:|
| `v8_full_spectrum_preflight` | `0.0` | `1641885696` | `0` | `0/0` |
| `v8_full_spectrum_system_ready` | `370.97334908600897` | `12480098304` | `0` | `0/0` |
| `v8_full_spectrum_group0_factor_ready` | `207.90935626099235` | `17674514432` | `0` | `0/0` |
| `v8_full_spectrum_group1_factor_ready` | `182.9128659699927` | `21893591040` | `0` | `0/0` |
| `v8_full_spectrum_group2_factor_ready` | `241.10231349102105` | `28171911168` | `0` | `0/0` |
| `v8_full_spectrum_lower_transform_ready` | `348.30305793098523` | `38749306880` | `0` | `0/0` |
| `v8_full_spectrum_upper_transform_ready` | `144.6964194290049` | `38749315072` | `0` | `0/0` |
| `v8_full_spectrum_symbol_ready` | `0.13321249099681154` | `38749315072` | `0` | `0/0` |
| `v8_full_spectrum_cleanup_complete` | `17.90213303899509` | `38874349568` | `0` | `0/0` |

旧几何 extent、empty-local probe 与 token/layout 的历史失败记录仍按原样保留；本节的 transform PASS 与 screen implementation failure 是两个独立结论。V8 failure roots 见本节及 [route ledger](route_signal_ledger.md)。

## 历史预运行快照

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
