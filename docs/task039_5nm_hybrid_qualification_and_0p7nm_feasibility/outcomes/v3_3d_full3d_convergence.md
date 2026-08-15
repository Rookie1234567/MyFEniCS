# V3-3/V3-4：1° Full3D direct 网格与 solver-stress anchor

本阶段只消费已经完成的 1°、5 nm、S 偏振、phi=0°、MPI8 Full3D direct raw。h5 和
h4.5 均只运行一次；h4/h3 没有启动。raw 与逐文件 SHA 见
[compact evidence](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_3d_full3d_convergence_v1.json)。

## 结论

| 项目 | 结论 | 边界 |
| --- | --- | --- |
| h5 own solve | `pass` | numerical own Gate 与 watchdog safety pass；命名 V3-6 stage/object telemetry 缺失 |
| h4.5 own solve | `pass` | numerical own Gate 与 watchdog safety pass；命名 V3-6 stage/object telemetry 缺失 |
| h5↔h4.5 | discrete scalar observables stable | R/T/A/A_volume 差约 `1e-8`；不是 2D reference 通过证明 |
| 2D Q8 ↔ h5 | `P2 fail` | persistent reduction/model-contract discrepancy；证据不支持归因于 h5 欠离散 |
| 2D Q8 ↔ h4.5 | `P2 fail` | 与 h5 的失败量几乎不变 |
| selected 3D anchor | `h5` | `best_available_solver_stress_anchor`，不是 1° physical qualification |
| h4 / h3 | `not_run_by_resource_policy` / `resource_not_qualified` | 不把未运行写成数值失败 |

P2 的意思是“3D 是否复现已经通过二维 TE reference 约束的归一化物理量”。它不是
solver own Gate：h5/h4.5 的 own solve 都通过，但两者对 Q8 的 R/A、selected field 和
主衍射功率差异基本相同。现有证据不支持把 P2 失败归因于 h5 欠离散；在资源安全范围内
继续 h 细化也没有依据。后续 Hybrid 结果必须标记为
`solver-stress`，不能称为物理资格通过。

## 三个层次的实测量

| case | mesh cells | full FE DoFs | active trace | assembled rows | NNZ used / allocated | factor NNZ corrected |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| h5 | 1680 | 1,127,502 | 336,960 | 337,560 | 283,118,032 / 298,007,160 | 2,753,000,000 |
| h4.5 | 2376 | 1,587,906 | 475,632 | 476,232 | 399,340,632 / 417,211,512 | 3,938,000,000 |

`factor NNZ corrected` 是由 MUMPS raw int32 溢出遥测恢复的计数，只作 telemetry，
不改 solver、不作为 own Gate。`matrix_memory_bytes=0` 的 PETSc INFO 不被当作真实内存。

| case | R | T | A_balance | A_volume | closure | residual |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| h5 | 0.7397397745 | 0.0002180403 | 0.2600421852 | 0.2600421852 | pass | `8.09e-10` |
| h4.5 | 0.7397397637 | 0.0002180419 | 0.2600421944 | 0.2600421944 | pass | `2.63e-10` |

## 2D↔3D P2 实际值

P2 使用 `R/T/A/A_volume` 的最大绝对差、独立 closure、selected `E_y/H_x/H_z` 相对
L2、主 m 阶功率加权差和 `n!=0 OR P` 泄漏。复杂振幅仅作 diagnostic。

| 比较 | scalar max abs | closure | E rel L2 | Hx rel L2 | Hz rel L2 | main-m weighted | leakage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Q8↔h5 | 7.1511079e-3 / `1e-4` | pass | 0.3936869 / `5e-3` | 1.4331359 / `1e-2` | 0.3563643 / `1e-2` | 9.7072779e-3 / `1e-3` | 1.1591e-22 / `1e-6` pass |
| Q8↔h4.5 | 7.1510971e-3 / `1e-4` | pass | 0.3936869 / `5e-3` | 1.4334247 / `1e-2` | 0.3563645 / `1e-2` | 9.7072360e-3 / `1e-3` | 1.3337e-23 / `1e-6` pass |

两次比较的 identity、common planes、closure 和 leakage 通过；scalar observables、
selected fields、main-m power Gate 失败。h5 与 h4.5 的 R/T/A/A_volume 绝对差分别约
`1.08e-8 / 1.60e-9 / 9.20e-9 / 9.19e-9`，而 2D↔3D 失败仍约 `7.15e-3`。
Q8 field-error 指标本身的变化也只作诊断，不能当作 h5↔h4.5 场数组的直接 L2 比较。
因此本阶段分类为 `reduction/model-contract discrepancy pending`；证据不支持把它归因于
h5 欠离散。

## 资源口径与停止决策

launcher 的 `*_mb` 字段来自 KiB/1024，按 MiB 解释，再以 MiB/1024 换算 GiB：

| case | RSS/PSS/USS (MiB) | RSS/PSS/USS (GiB) | elapsed / factorization |
| --- | ---: | ---: | ---: |
| h5 | 96151.168 / 94117.470 / 93793.180 | 93.8976 / 91.9116 / 91.5949 | not split in this record / 4617.46 s |
| h4.5 | 128565.934 / 126493.808 / 126173.145 | 125.5527 / 123.5291 / 123.2160 | 10112.04 / 9711.64 s |

两个 run 都 swap=0、warning/critical 未触发，采样周期 0.25 s。按 h4.5 实测 RSS
反推 h4：

```math
RSS_{h4} \approx 125.5527\ \mathrm{GiB}\left(\frac{4.5}{4}\right)^4
\approx 201.1\ \mathrm{GiB}.
```

这高于 Review 的 `<190 GiB` startup gate，且接近用户覆盖的
`224000000000 bytes = 208.6162567138672 GiB` hard stop，故 h4
`not_run_by_resource_policy`。h3 的既有预测区间为 `360–630 GiB`，记为
`resource_not_qualified`。预测是 derived/predicted，不是 measured。

两个正式 raw 都只有 `progress_3d.jsonl` 和 launcher `resource_authority`；命名的
`process_tree_samples.jsonl`、`memory_stages.jsonl`、`memory_object_ledger.json`
在这两次 raw 中不在。不得把缺失命名 artifact 补写成存在；后续 V3-5 prep 只检查
现有接线，不在这里宣称 stage-aligned ledger 已完成。

## 阶段边界

V3-3/V3-4 至此受控收口：h5 选为 best available solver-stress anchor，P2 未建立。
这不阻止 Review 授权的 V3-5 h5 Hybrid direct algebra/solver-stress 诊断，但不提升
Hybrid 的物理资格。V3-5 本轮只做 input/profile/adapter 与 focused tests 准备；正式
Hybrid PDE、V3-6 及以后均 `not_run`。
