# 结果、JSON 与 ParaView：从文件夹判断一次计算是否可信

## 1. 功能与物理图景

求解结束不等于物理结果可信。本页说明普通结果、benchmark artifact、轻量 canonical record、official R/T/A 和 ParaView 场文件之间的关系。

## 2. 当前能力状态

| 输出 | 状态 |
|---|---|
| 2D/3D `run_summary.json` | 稳定 |
| serial VTU | 稳定 |
| MPI rank-local VTU + PVD | 稳定 |
| benchmark lightweight JSON | 自动 Gate |
| 大型场文件入 Git | 禁止，保持 gitignored |

## 3. 运行前提

计算必须 exit code 0；非收敛解不能用后处理生成的 R/T/A 冒充 official 结果。先读 `solver_log.txt` 和 residual，再打开场。

## 4. PyCharm 运行配置

普通 Run 使用 `src/main.py`；在 `Edit Configurations | Logs` 可将 console 保存到用户路径。不要把日志重定向到 canonical `records/`。

## 5. 输出位置由哪里控制

| 入口 | 默认 |
|---|---|
| 普通 runner/main | `results/` |
| benchmark case | `benchmarks/artifacts/cases/<id>/` |
| canonical lightweight evidence | `benchmarks/cases/<id>/records/` 或顶层兼容 records |

`results_root`/`--results-root` 只改变 artifact 根，不改变物理模型。

## 6. 典型 2D 目录树

```text
<run>/
├── run_summary.json
├── solver_log.txt
├── mesh.msh
├── fields_for_paraview.vtu
├── diffraction_orders.json/csv
├── dtn_port_power_metrics.json
├── dtn_port_diffraction_orders.json/csv
├── dtn_auxiliary_power_metrics.json
└── dtn_auxiliary_amplitudes.json
```

最后两个文件只在 TM auxiliary DtN 路径出现。

## 7. 典型 3D 目录树

```text
<run>/
├── run_summary.json
├── solver_log.txt
├── mesh.msh
├── fields_3d_for_paraview.vtu
├── fields_3d_for_paraview_parallel.pvd
├── fields_3d_for_paraview_rank0000.vtu
├── diffraction_orders_3d.json/csv
└── dtn_port_* / memory telemetry
```

serial 使用单 VTU；MPI 使用 PVD 总入口和 rank-local VTU。

## 8. 参数和单位

几何、网格、波长以 nm 存储；场求解采用归一化入射幅值。`incident_e0_v_per_m` 只控制物理单位显示，不改变无量纲 R/T/A。

## 9. CLI 等价命令

```text
python src/main.py --preset 3d_stage1_airbox_smoke --results-root results/tutorial
python src/main.py --preset 2d_complex_absorption --results-root results/tutorial
```

## 10. 关键 JSON 字段

| 字段 | 含义 |
|---|---|
| `reduced_linear_residual` / `linear_system_relative_residual` | 线性系统真残差 |
| `reported/condensed/full_augmented_true_residual` | workstation 三种残差口径 |
| `num_*_dofs` | FE/aux/reduced 规模 |
| `R_total/T_total/A_volume` | 功率比例 |
| `energy_closure_error` | record 明确采用的能量闭合口径 |
| `total_peak_rss_mb` | MPI rank 峰值之和 |
| `artifact_directory` | 完整场的来源 |
| `metadata.commit_sha` | 生成数值的源提交 |

## 11. Official 与 diagnostic

| 数据源 | 身份 |
|---|---|
| DtN auxiliary modal amplitudes | TM/3D official |
| DtN boundary trace projection | explicit reference；TE 当前 official |
| A_volume | official absorption |
| E/H Fourier probe | diagnostic_only |
| sampled Poynting | consistency/diagnostic |

有损 Case003 即使 probe closure 偏离，也不得覆盖 modal official 结果。

## 12. ParaView 实际步骤

1. serial 打开 `fields*_for_paraview.vtu`；MPI 打开 `.pvd`。
2. `Apply` 后选择 `Surface` 或 `Slice`。
3. 颜色选择 `E_total_abs`；若要分量，选择 `E_total_real` 并用 Calculator。
4. 周期单元边界用 `Outline` 核对，避免把单个 rank 分片当成全域。
5. 比较两次运行时固定 Color Map range，不使用每次自动缩放。

## 13. 成功 Gate

```text
residual 通过案例 expected.json
official R/T/A 非负并满足能量阈值
config 与期望物理模型一致
场文件非空、网格边界正确
record provenance 指向真实 artifact
```

## 14. 常见错误

| 现象 | 原因 |
|---|---|
| 只看到一个分片 | MPI 时打开了单 rank VTU |
| R/T/A 有值但 residual 失败 | 后处理仍执行，结果不可接纳 |
| record 与场目录对不上 | 复制了数值但未更新 provenance |
| `A_balance` 与 `A_volume` 差大 | 功率平面、模态选择或材料标签问题 |
| VTU 很大 | 正常 artifact；不要加入 Git |

## 15. 从 smoke 形成新 record

先把完整运行写到新的 artifact 目录，再人工和自动检查 residual、R/T/A、RSS、commit 和物理模型。只有固定问题和阈值后，才把最小 JSON 提升为 canonical record；场文件仍留在本地。

## 16. 链接

- RTA 理论：[`../theory/official_and_diagnostic_rta_methods.md`](../theory/official_and_diagnostic_rta_methods.md)
- 输出代码：[`../reference/code_walkthrough/40_output_schema_and_visualization.md`](../reference/code_walkthrough/40_output_schema_and_visualization.md)
- Case003：[`../../benchmarks/cases/003_2d_te_tm_complex_absorption/README.md`](../../benchmarks/cases/003_2d_te_tm_complex_absorption/README.md)
- Benchmark 总览：[`../../benchmarks/README.md`](../../benchmarks/README.md)
