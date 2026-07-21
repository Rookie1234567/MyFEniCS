# Task034 Phase D：p3/h3 更细离散参考与重新排名

## 1. 结论

Phase D 已按 assembly-only → factorization-only → full-solve → Hybrid funnel → same-degree closure → reranking 的顺序完成。正式分类为：

```text
p3_h3_reference_available = true
p3_h5_to_h3_grid_change = measured
p3_h7p5_equal_accuracy_under_new_reference = pass
p2_h3_equal_accuracy_under_new_reference = pass
grid_convergence_proven = false
continuum_reference = false
```

`p3/h3` 是当前更细的独立离散参考，不是 continuum reference，也没有单凭三个离散点证明 grid convergence。Task033 D1 的等精度阈值没有放宽：`p2/h3` 相对新 `p3/h3` reference 的 12 项误差定义 baseline threshold vector；候选必须逐项不劣于该向量，并单独满足 full true residual `<= 1e-9`。

正式聚合状态为 `p3_h3_reference_and_reranking_pass`。在该规则下，`p3/h7.5` 12 项全部通过；其最差分量相对 p2/h3 阈值的比值为 `0.89910967`。这保留了 Task033 的固定 p 等精度正结论，但参考边界已从 p3/h5 更新为更细的 p3/h3。

## 2. 身份与执行边界

| 字段 | 值 |
|---|---|
| WSL | Ubuntu 24.04，native `.venv` |
| full3D MPI | MPI4 |
| direct solver | PETSc `preonly` + LU/MUMPS |
| p3/h3 full3D source | `685c9a7e8cd9499070e5d1abb11957f6014444e7` |
| p3/h3 Hybrid source | `22ee479b65319f3f57a10dffe4d3ee6ae514e055` |
| p2/h3 reranking source | `58ace07a2b6990a2f7680ca4c8ae1a74be4d9064` |
| D4 aggregation source | `6f1c0fbef1ecfcf9d27c1a9149fd25a21e0a1e22` |
| heavy-run concurrency | one-heavy-case-at-a-time |
| job swap | 全部正式运行均为 0 |
| ordinary default | unchanged；新路径显式 opt-in |

在 clean `6f1c0fb...` 上重跑的 numerical-blob audit 为 formal pass；记录 SHA-256 为 `63406d45c900ea6bf2a75e0bb6d149f1bbf16260a21818760e5367715eabdce4`。`hcurl_multilevel.py` 的历史 allowlisted 变更仍要求其对应 PDE rerun，但不改变本节 MUMPS full3D / Hybrid direct reference 的身份；该要求没有被改写为无需验证。

## 3. p3/h3 分阶段 direct reference

| Gate | status | rows / assembled NNZ | factor NNZ | memory authority | solver elapsed | swap |
|---|---|---:|---:|---:|---:|---:|
| assembly-only | `assembly_calibration_pass` | 656,405 / 157,785,425 | 未进入 | 19.167 GiB | 778.96 s | 0 |
| factorization-only | `factorization_calibration_pass` | 656,405 / 157,785,425 | 1,288,954,261 | 40.667 GiB | 2259.35 s | 0 |
| full-solve | `full3d_reference_pass` | 656,405 / 157,785,425 | 1,286,075,117 | 39.122 GiB | 2281.13 s | 0 |

三层 Gate 均通过，未触发 memory warning、termination 或 timeout。full-solve 的 `KSPSetUp` 为 1495.43 s，而 `KSPSolve` 仅 1.57 s；耗时主体是 MUMPS 的符号/数值分解和 fill，而不是求解前的普通 setup。mesh、function-space、Floquet/MPC 和 variational-form 等前置步骤都在校准量级内，没有出现异常建立时间。

### 3.1 p3/h3 official reference

| 指标 | 实测值 |
|---|---:|
| Nédélec DoF / DtN auxiliary DoF | 656,325 / 80 |
| full true relative residual | `6.9668149109e-11` |
| R_total | 0.000789467957371 |
| T_total | 0.602514984138200 |
| A_balance | 0.396695547904429 |
| A_volume | 0.396695547904359 |
| R+T+A_volume−1 | `-6.9056e-14` |
| compact reference NPZ SHA-256 | `16fd415b876981218e53c0b8d630fc21cb3604b9cdbc5ca87da554643282313a` |

reference archive 包含相同的 10/30/60/90/110 nm 五平面 E/H、10/110 nm 两侧切向 E/H、significant diffraction orders、official R/T/A 与 volume absorption。

## 4. p3/h3 Hybrid funnel 与受控负结果

| M | run identity | formal | memory | time | true residual | 失败 Gate |
|---:|---|---|---:|---:|---:|---|
| 80 | final | pass | 8.698 GiB | 881.93 s | `6.762e-12` | 无 |
| 120 | first final-SHA attempt | fail | 9.731 GiB | 1044.99 s | `1.885e-11` | `biorthogonality_identity_error_le_1e-6` |
| 120 | repeat2 | pass | 9.806 GiB | 1002.97 s | `7.632e-12` | 无 |
| 160 | formal final | pass | 10.762 GiB | 1113.84 s | `3.903e-11` | 无 |

M120 首次运行的 forward biorthogonality error 为 `1.719202e-6`，超过固定 `1e-6` Gate；该记录保持 `formal_not_pass`，未删除、未放宽阈值。相同 SHA、相同 M、相同阈值的 repeat2 得到 forward/backward `6.129e-7 / 6.176e-7` 并正式通过，因此同时保存 repeatability negative 和通过样本。

正式 funnel 使用 M80、通过的 M120 repeat2 和 M160：

| pair | max abs R/T/A delta | significant power max relative delta | significant amplitude max relative delta | 分类 |
|---|---:|---:|---:|---|
| M80 → M120 | `1.3734e-11` | `8.5804e-9` | `6.2261e-9` | strong pass |
| M120 → M160 | `5.954e-13` | `2.767e-9` | `1.655e-9` | strong pass |

M160 被选中。M120→M160 已通过强 Gate，因此条件性 M240 没有数值必要，也未运行。

## 5. p3/h3 same-degree closure

M160 相对同阶 p3/h3 full3D 的全部 16 个 Hybrid Gate 通过：

| 指标 | Hybrid M160 对 full3D |
|---|---:|
| abs(ΔR) / abs(ΔT) / abs(ΔA_balance) | `6.231e-10 / 5.440e-9 / 6.063e-9` |
| abs(ΔA_volume) | `6.066e-9` |
| 五平面 max E/H relative L2 | `1.059e-6 / 2.362e-5` |
| 上下接口 max Et/Ht relative L2 | `1.059e-6 / 6.213e-5` |
| significant-order power max/RMS | `1.242e-3 / 5.689e-4` |
| significant-order amplitude max/RMS | `1.005e-3 / 4.971e-4` |
| Hybrid full true residual | `3.903e-11` |
| Hybrid R+T+A_volume−1 | `2.367e-12` |

这证明 selected M160 在同一 degree/h 的 Hybrid/full3D observable closure；它不把 Hybrid 结果升级为 continuum solution。

## 6. p2/h3 reranking reference 补跑

旧 p2/h3 descriptor 的 raw archive 已不在本机，因此没有用缺失 archive 冒充 `measured`。在 fixed-geometry CLI 明确支持 p2/h3 后，按相同 staged Gate 在 clean `58ace07...` 上重新运行：

| Gate | status | rows / NNZ | factor NNZ | memory | stage time | swap |
|---|---|---:|---:|---:|---:|---:|
| assembly-only | pass | 198,518 / 21,317,860 | 未进入 | 3.283 GiB | 57.92 s | 0 |
| factorization-only | pass | 198,518 / 21,317,860 | 249,341,732 | 7.656 GiB | 183.31 s | 0 |
| full-solve | pass | 198,518 / 21,317,860 | 250,318,324 | 7.739 GiB | 195.99 s | 0 |

post-factorization full-solve 预测中心/上界为 `7.855/11.783 GiB` 和 `195.99/293.99 s`，远低于 `155.085 GiB` warning。full-solve 实测 `KSPSetUp=137.80 s`、`KSPSolve=0.299 s`、true residual `9.739e-12`；再次确认耗时来自 direct factorization，direct solve 前 setup 正常。p2 reference NPZ SHA-256 为 `f1d3215692d538742194a963d59cfe0a7bfbf9d6b0bce8b0998cf7dcfd14b90c`。

## 7. 相对 p3/h3 的 12 项重新排名

下表全部误差都相对同一 p3/h3 finer discrete reference。p2/h3 列是 Task033 D1 baseline threshold；候选通过要求逐行 `<=` p2/h3，而不是只看一个平均分。

| metric | p2/h3 threshold | p3/h7.5 | p3/h5 | p3/h3 Hybrid M160 |
|---|---:|---:|---:|---:|
| abs(ΔR) | 0.00382356 | 0.00230126 | 0.000300639 | `6.231e-10` |
| abs(ΔT) | 0.01886163 | 0.01135412 | 0.00189251 | `5.440e-9` |
| abs(ΔA_balance) | 0.01503806 | 0.00905286 | 0.00159187 | `6.063e-9` |
| abs(ΔA_volume) | 0.01503806 | 0.00905286 | 0.00159187 | `6.066e-9` |
| five-plane max E relative L2 | 0.558494 | 0.349103 | 0.062012 | `1.059e-6` |
| five-plane max H relative L2 | 0.560283 | 0.351224 | 0.064865 | `2.362e-5` |
| interface max Et relative L2 | 0.558494 | 0.349103 | 0.062012 | `1.059e-6` |
| interface max Ht relative L2 | 0.510665 | 0.329062 | 0.060054 | `6.213e-5` |
| significant power max | 0.830414 | 0.746634 | 0.277881 | 0.001242 |
| significant power RMS | 0.382973 | 0.333521 | 0.092701 | 0.000569 |
| significant amplitude max | 0.814684 | 0.674516 | 0.210857 | 0.001005 |
| significant amplitude RMS | 0.447700 | 0.380274 | 0.079631 | 0.000497 |
| full true residual（独立 Gate） | `9.739e-12` | `1.022e-11` | `1.222e-11` | `3.903e-11` |

按“相对 p2/h3 阈值的最差分量比”只做可读性排序（不替代逐项 Gate）：

| rank | candidate | worst ratio to p2/h3 threshold | 12 项 no-worse |
|---:|---|---:|---|
| 1 | p3/h3 Hybrid M160 | 0.001495 | pass |
| 2 | p3/h5 | 0.334629 | pass |
| 3 | p3/h7.5 | 0.899110 | pass |
| 4 | p2/h3 baseline | 1.000000 | baseline pass |

p2/h3 的 `pass` 表示它提供完整、有限且 residual 合格的 baseline threshold vector，不是与自身做零误差比较。p3/h7.5 的每个物理分量都小于该 baseline，因此 `p3_h7p5_equal_accuracy_under_new_reference=pass`；没有用资源较低来抵消任何物理失败。

## 8. 证据

tracked 正式聚合记录：

```text
benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/p3_h3_reference_summary.json
payload_sha256 = e0c69bccd2f1095388013e050069865878a22f3482853edcbffefa547d83f72d
file_sha256 = d9ccbcceab798095e9af30257a73d52d3e3c1cd6c2acf10c5f45ffe5d3879ab9
```

关键 ignored 证据继续保存在 `benchmarks/artifacts/task034/phase_d/`，tracked summary 保存 descriptor、run summary、NPZ、diffraction orders、Hybrid watchdog、funnel 和 numerical-blob audit 的路径与 SHA-256。D4 派生 descriptor 只补入 raw diffraction orders hash，没有改变任何数值载荷：

```text
p2/h3 D4 descriptor = dfa1c8c335130410e05b6ba296c9243d0d33d2e234789f48232cc583ad355f36
p3/h3 D4 descriptor = 679cf76c8c653cb7deb792deb7ff7c912edc805ed75713d3656c8b374299db9d
```

## 9. 限制与下一阶段输入

1. `p3/h3` 仍是 finer discrete reference，不是 continuum reference。
2. p3/h7.5→h5→h3 的误差确实随细化降低，但本阶段不据此单独声明独立的严格 grid-convergence proof。
3. 排名的 worst ratio 只用于阅读；正式判定仍是 12 项逐项 no-worse 加 residual Gate。
4. 内存和 wall time 是实测 provenance，不混入物理误差排名。
5. Phase D 已为 Phase E p4/h5 staged study 和补充任务书 Phase F fixed-geometry convergence 提供 p3/h3 anchor；后续仍必须逐候选重新经过资源 Gate。
