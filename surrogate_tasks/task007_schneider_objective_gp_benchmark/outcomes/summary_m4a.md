# Task007 M4A outcomes summary

## 范围与最终状态

M4A 严格执行 Review V2 的无 FEM 稳健性闭合。所有计算只调用冻结 Task006 `legendre_3` response oracle；没有运行新 FEM、没有重试 Task006 失败点、没有修改 Task006 model lock，也没有覆盖 M3/V1 原始 artifacts。M4 实现身份绑定 `34d52d075842f177f2c055f8f0ef5cdf48d63d67`。

| audit | data identity | result | Gate/status | evidence |
|---|---|---:|---|---|
| independent oracle MAP stability | 48 M3 target/contract/noise rows | 48/48 | PASS | `M4_MAP_STABILITY_AUDIT.json` |
| standalone J1/P2 acquisition replay | 12 targets × N1/N2 | 24/24 | PASS | `M4_ACQUISITION_REPLAY_AUDIT.json` |
| response-blind stopping | M3 J1 targets, P1/P2, N1/N2 | P2/N2 pass; other three controlled negatives | readiness not fully passed | `M4_RESPONSE_BLIND_STOPPING.json` |
| new-noise Monte Carlo | 12 targets × 2 noise × 10 seeds | 240 measurements, P2/N2 and P1/N2 pass | N1 readiness negatives retained | `M4_NOISE_MONTE_CARLO.json` |
| initialization/cost study | I0–I4, J1/J0, N1/N2 | 20 summary cells | diagnostic complete | `M4_INITIALIZATION_COST_STUDY.json` |
| GP warning taxonomy | all 1,361 M3 updates | 2,028 warnings, 196 boundary collisions | diagnostic complete | `M4_GP_WARNING_TAXONOMY.json` |

## MAP 与 acquisition 独立性

MAP stability 使用与 M3 不同的 Differential Evolution + bounded L-BFGS-B polish。48 个组合满足：

- `abs(F_new-F_old) <= 1e-6 * max(1, abs(F_old))`；
- `|dh| <= 0.02 nm`、`|dw| <= 0.005 nm`；
- 没有 objective-equivalent 但坐标不一致的多极小值记录。

Standalone acquisition replay 不调用 M3 `run_sequential_bo` 或 `_continuous_acquisition`。它从 stored initial `(x,F)` 逐步重拟合 ExactARDGP，独立重算 EI、低 EI fallback、chosen query 和 objective；24/24 的 geometry、EI、mode、query count、final best 均一致。Case148 checker 对这些结果及 hash 重新检查。

## Response-blind 与 noise Monte Carlo

运行时停止规则不读取 hidden oracle MAP：

```text
max grid EI < 1e-3 连续两次
且 best log-objective improvement < 1e-3 连续三次
否则最多 20 次 online query
```

| method | noise | response-blind MAP hit | median queries | p90 | Gate |
|---|---|---:|---:|---:|---|
| P1 Sobol12 | N1 | 12/12 | 20.0 | 20.0 | controlled negative |
| P1 Sobol12 | N2 | 11/12 | 10.5 | 15.9 | controlled negative |
| P2 Sobol37 | N1 | 12/12 | 11.0 | 14.9 | controlled negative |
| P2 Sobol37 | N2 | 12/12 | 7.0 | 8.0 | PASS |

10-seed primary J1 Monte Carlo 的 120 个 realization/方法/噪声组合结果为：

| method | noise | MAP hits | fraction | median | p90 | max | Gate |
|---|---|---:|---:|---:|---:|---:|---|
| P1 Sobol12 | N1 | 115/120 | 0.958 | 20.0 | 20.0 | 20 | controlled negative |
| P1 Sobol12 | N2 | 118/120 | 0.983 | 10.0 | 14.0 | 20 | PASS |
| P2 Sobol37 | N1 | 115/120 | 0.958 | 10.0 | 13.0 | 20 | controlled negative |
| P2 Sobol37 | N2 | 116/120 | 0.967 | 7.0 | 10.0 | 13 | PASS |

N1 的负结果来自 response-blind stopping 成本/稳定性 Gate（P1 median 20；P2 median 10），不是将失败 target 删除、改变容差或重新选择 noise seed。该结果阻止 physical Level-B pilot 自动解锁。

## 初始化成本与 warning 诊断

初始化研究只比较 I0 existing train37、I1 Sobol12、I2 Sobol37、I3 train37+Sobol6、I4 train37+Sobol12。新增物理 FEM 估算按“相对于已存在 train37 的新 geometry 数 × 三个固定照明”计数；I1/I2 的 response library 若重新建立，分别需要 36/111 个新 FEM evaluation，I3/I4 需要 18/36 个。

GP warning taxonomy 从 M3 全部 1,361 个 update 重新拟合得到：2,028 个 selected-run warnings、196 个 boundary collisions，其中 `hyperparameter_boundary_convergence=200`、`other_convergence_warning=1828`。报告包含 method、contract/noise、observed count、selected jitter、fitted kernel、length-scale、constant amplitude、LML 和代表 warning；没有修改 kernel bounds。

## 保留边界与下一步

- Task007 V1 全部 replay、P3 controlled-negative 和 M3 全部 traces 保持不变；P3 仍不是 Schneider 方法失败。
- M4A 只是同一 Legendre-3 oracle 内的 self-consistent benchmark，不包含 Full3D discretization error、surrogate discrepancy、FEM numerical failure 或实验 covariance。
- Case148 checker `pass` 不等于 physical surrogate 或 inversion 资格通过。
- `new_fem_count=0`；physical online-FEM BO、正式反演、Task006 retry 和参数扩展均保持禁止，等待 Review V3。

## 证据入口

- [M4 implementation identity](M4_IMPLEMENTATION_IDENTITY.json)
- [MAP stability](M4_MAP_STABILITY_AUDIT.md) · [acquisition replay](M4_ACQUISITION_REPLAY_AUDIT.md)
- [response-blind stopping](M4_RESPONSE_BLIND_STOPPING.md) · [noise Monte Carlo](M4_NOISE_MONTE_CARLO.md)
- [initialization cost](M4_INITIALIZATION_COST_STUDY.md) · [GP warning taxonomy](M4_GP_WARNING_TAXONOMY.md)
- [Case148 checker record](../../../benchmarks/cases/148_task007_m4a_robustness/records/case148_check.json)
