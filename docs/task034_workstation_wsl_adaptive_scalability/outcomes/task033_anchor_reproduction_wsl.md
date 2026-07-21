# Task033 关键锚点的 WSL 原生复现

## 结论

在已资格化的 Ubuntu 24.04 WSL 原生环境中，p3/h7.5 与 p3/h5 的 S polarization、MPI8 Full3D 和 Hybrid M160 均通过 full true residual、official R/T/A、zero job swap 与 same-degree closure。正式状态为 `wsl_task033_anchor_reproduction_pass`；这复现关键锚点，不升级 Task033 原始范围或把离散解称为 continuum solution。

数据身份：固定结构 physical identity SHA-256 `abb8613b3c0a9f78ce11def2695d2e3b590ba0c37b15534027fe3348345f4551`；环境 ID `task034-wsl-ubuntu-24.04-native`。结构化记录位于 `benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/wsl_anchor_summary.json`，上游 compact authority 为 Case093 `records/convergence_summary.json`。

## official R/T/A 与 residual

| 点 | 方法 | h (nm) | R | T | A_volume | true residual | peak GiB | evidence SHA-256 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| p3/h7.5 | Full3D | 7.5 | 0.003090727450 | 0.591160863329 | 0.405748409221 | `7.682e-12` | 4.610 | `0efc1365...` |
| p3/h7.5 | Hybrid M160 | 7.5 | 0.003090647382 | 0.591159679406 | 0.405749673156 | `3.164e-12` | 3.614 | `0cdf04a4...` |
| p3/h5 | Full3D | 5.0 | 0.001090107012 | 0.600622478293 | 0.398287414695 | `6.982e-12` | 9.040 | `065aa9af...` |
| p3/h5 | Hybrid M160 | 5.0 | 0.001090095685 | 0.600622368221 | 0.398287536096 | `1.055e-11` | 4.908 | `8e18d689...` |

## same-degree closure

| 点 | abs ΔR | abs ΔT | abs ΔA_volume | selected M/direction | funnel SHA-256 | 判定 |
|---|---:|---:|---:|---:|---|---|
| p3/h7.5 | `8.007e-8` | `1.184e-6` | `1.264e-6` | 160 | `2202dea1...` | pass |
| p3/h5 | `1.133e-8` | `1.101e-7` | `1.214e-7` | 160 | `cda75529...` | pass |

两点均绑定 fresh Full3D reference、Hybrid descriptor、QEP/funnel 和完整 field/order observable。它们同时参与 Case093 长期 benchmark 冻结；后续 p3/h3 finer discrete reference 对 Task033 等精度结论的重新排名见 `p3_h3_reference_and_reranking.md`。
