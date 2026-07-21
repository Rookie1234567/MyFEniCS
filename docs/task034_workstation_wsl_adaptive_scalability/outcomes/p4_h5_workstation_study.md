# Task034 Phase E：p4/h5 工作站受控研究

## 1. 结论

Phase E 已按 E0 assembly-only → E1 p4 QEP/four-mode trace 与 Hybrid funnel →
E2 factorization-only → E3 full solve → fresh same-SHA Hybrid funnel 与同阶 closure
的顺序完成。正式分类为：

```text
phase_e_outcome = p4_same_degree_closure_pass
p4_clear_engineering_accuracy_benefit_vs_p3_h5 = true
assembly_performance_difference_candidate = true
grid_convergence_proven = false
continuum_reference = false
```

所有正式运行均满足 one-heavy-case-at-a-time、source clean/stable、现场 watchdog、
zero job swap 和固定 true residual/Gate 阈值。未运行 p4/h3，也未因耗时放宽任何阈值。

## 2. 多 SHA 证据边界

Phase E 是按阶段 hardening 的多 commit 证据链，不能冒充全部同一 SHA：

| 阶段 | clean full SHA |
|---|---|
| E0 assembly calibration | `dc81ae75c0253e5f2d8070613e9ff82f33eab3e4` |
| E2 factorization 与 E3 full3D | `4e1143f9a1e91ff703e871fcb74e5f6703223a82` |
| fresh Hybrid M80/M120/M160 与 closure | `a6f5a0de0a64d4af46a198878fa21ff7298f38d0` |

后继阶段只通过记录内的 audited source-compatible descendant Gate 消费前序证据。
Case090 core compatibility、p4 authority compatibility、full3D descriptor binding 和
Hybrid reference binding 均通过；不存在把旧 bootstrap 检查冒充 Phase A 或把不同 SHA
改写成同 SHA 的情况。

## 3. full3D 分级 Gate

| Gate | status | rows / assembled NNZ | factor NNZ | memory | elapsed | swap |
|---|---|---:|---:|---:|---:|---:|
| E0 assembly-only | `assembly_calibration_pass` | 339,972 / 155,421,000 | 未进入 | 19.414 GiB | 1242.21 s | 0 |
| E2 factorization-only | `factorization_calibration_pass` | 339,972 / 155,421,000 | 561,990,384 | 27.049 GiB | 1712.71 s | 0 |
| E3 full solve | `full3d_reference_pass` | 339,972 / 155,421,000 | 562,270,960 | 26.786 GiB | 1701.84 s | 0 |

factorization-only 没有进入 `KSPSolve`。它的 `KSPSetUp` 为 408.336 s；full solve
重复样本为 393.344 s，factor NNZ 与峰值内存也一致，因此直接分解可重复且资源安全。

### 3.1 `KSPSetUp` 与求解前建立耗时

本 Case 的 PETSc profile 是 `KSP=PREONLY`、`PC=LU`、MUMPS。这里：

- `KSPSetUp` 执行 MUMPS 符号分析与数值 LU 分解，是直接法的主要计算阶段；
- `KSPSolve` 在已分解矩阵上完成回代，不代表全部“直接法求解过程”；
- full solve 的 `KSPSetUp=393.344 s`，`KSPSolve=0.724 s`，这一比例合理。

full solve 的普通前置步骤为：

| 步骤 | 实测 |
|---|---:|
| mesh build | 0.912 s |
| function-space setup | 0.086 s |
| Floquet/MPC total | 0.880 s |
| variational-form setup | 0.021 s |
| augmented copy/insert/finalize | 约 23.22 s |

这些步骤没有异常。长耗时来自 base matrix assembly（E0 为 1219.277 s，full
重复为约 1278.480 s）和 LU factorization，而不是 mesh、Floquet、form 或增广建立。

### 3.2 official full3D reference

| 指标 | 值 |
|---|---:|
| true relative residual | `3.3539739621e-11` |
| R_total | 0.000766313377102 |
| T_total | 0.602677530502883 |
| A_balance | 0.396556156120015 |
| A_volume | 0.396556156119943 |
| R+T+A_volume−1 | `-7.1942e-14` |

## 4. p4 Hybrid funnel

fresh same-SHA funnel 结果：

| M | status | memory | total | true residual | swap |
|---:|---|---:|---:|---:|---:|
| 80 | `measured_shard_pass` | 5.049 GiB | 558.97 s | `5.182e-12` | 0 |
| 120 | `measured_shard_pass` | 5.498 GiB | 634.19 s | `5.726e-12` | 0 |
| 160 | `measured_shard_pass` | 5.961 GiB | 734.22 s | `7.031e-12` | 0 |

M120→M160 的 max abs R/T/A delta 为 `2.4092e-14`，significant-order power
和 complex-amplitude 最大相对变化为 `1.0745e-9 / 5.4781e-10`。强收敛 Gate
通过并选择 M160；M240 的条件没有触发，因此未运行。

## 5. Hybrid M160 对同阶 full3D closure

| 指标 | Hybrid M160 对 full3D |
|---|---:|
| ΔR / ΔT / ΔA_balance | `-1.426e-10 / -9.143e-10 / 1.057e-9` |
| ΔA_volume | `1.060e-9` |
| 五平面 max E/H relative L2 | `2.054e-7 / 1.026e-5` |
| 上下接口 max Et/Ht relative L2 | `2.054e-7 / 6.218e-5` |
| significant-order power max/RMS | `4.362e-4 / 2.186e-4` |
| significant-order amplitude max/RMS | `4.277e-4 / 1.961e-4` |
| Hybrid true residual | `7.031e-12` |
| Hybrid R+T+A_volume−1 | `3.257e-12` |

M160 的 16 个 measurement Gate 全部通过；full3D NPZ、descriptor 和 official
diffraction-order source 均有 SHA-256 binding。同阶 closure 证明 p4/h5 的
Hybrid/full3D 耦合链可用，不把结果升级为 continuum solution。

## 6. p4 的工程精度收益

相对同一个 p3/h3 finer discrete reference，p4/h5 的 12 项 Task033 D1 误差全部
小于 p3/h5。代表性对比如下：

| metric | p3/h5 | p4/h5 |
|---|---:|---:|
| abs(ΔR) | `3.006e-4` | `2.315e-5` |
| abs(ΔT) | `1.893e-3` | `1.625e-4` |
| 五平面 max E/H | `6.201e-2 / 6.486e-2` | `5.473e-3 / 8.450e-3` |
| 接口 max Et/Ht | `6.201e-2 / 6.005e-2` | `5.473e-3 / 5.452e-3` |
| diffraction power max/RMS | `2.779e-1 / 9.270e-2` | `2.963e-2 / 9.480e-3` |
| diffraction amplitude max/RMS | `2.109e-1 / 7.963e-2` | `2.159e-2 / 7.480e-3` |

因此 `p4_clear_engineering_accuracy_benefit_vs_p3_h5=true`。这只是离散工程收益；
p4/h5 与 p3/h3 既不同 degree 又不同 h，本阶段仍保持
`grid_convergence_proven=false` 和 `continuum_reference=false`。

## 7. assembly 性能差异

当前 E0 base assembly 相对历史 463.109 s 为约 2.633 倍，full 重复为约 2.761 倍。
同机 p3 锚相对旧环境总时长也约为 2.394 倍；同时 p4 Hybrid M80/M120/M160 的
two-local-FEM assembly 都稳定在约 372.5 s，几乎不随 M 变化。现有证据更支持
host/WSL/MPI/hardware throughput 是主要混杂因素，而不是 p4 数值路径单独退化。

该问题保留为 `assembly_performance_difference_candidate`，不改写为“无问题”或
“代码回归”。Phase F 重型运行前先做 fresh same-SHA MPI8 环境资格化和 assembly
scaling 对照；只有同环境、同 SHA 证据显示异常，才进入 assembly core 优化与受影响
PDE 证据重跑。

## 8. 证据与下一步

tracked 紧凑记录：

```text
benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/p4_h5_workstation_summary.json
payload_sha256 = a20075a79e3404a5fd4efc41aef88e8320242257e15c8212679f6b1b2553b675
file_sha256 = f81dc4b4d6f62d2471a43cd270ea7de456329b65374fd724710e8d033c639b58
```

重型原始记录继续位于 gitignored `benchmarks/artifacts/task034/phase_e/`，tracked
summary 绑定 assembly、factorization、full3D、descriptor、NPZ、official orders、
Hybrid M80/M120/M160、funnel、p4 four-mode trace 和 p3/h3 reference 的 SHA-256。

Phase E 已完成。下一步仍须先通过 MPI8/16 轻量资格化，再按补充任务书执行 Phase F
fixed-geometry convergence；不得从当前单点结果推导 0.7 nm 可行性或连续解收敛。
