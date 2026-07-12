# 结果目录与 ParaView

## 两类输出根目录

| 根目录 | 内容 | Git 策略 |
|---|---|---|
| `results/` | 用户每次普通运行的完整案例目录 | 全部忽略，可自行删除 |
| `benchmarks/artifacts/` | 基准的网格、场和完整日志 | 全部忽略 |
| `benchmarks/records/` | 小型结果、身份、残差、RSS、RTA | 提交并由 checker 验证 |

## 案例目录中先看什么

| 文件 | 用途 |
|---|---|
| `run_summary.json` / `all_run_summary.json` | 配置、矩阵、残差、计时、功率总表 |
| `run_log.txt` | 阶段进度、求解器选择、失败位置 |
| `power_summary.csv` | R/T/A 及闭合误差的扁平表 |
| `power_metrics*.json` | 2D modal/probe/DtN 细项 |
| `power_metrics_3d.json` | 3D official port power 与体吸收 |
| `fields*.vtu` / `.pvd` | ParaView 场；MPI 每 rank 分片由 `.pvd` 聚合 |
| `progress.json` | 长运行当前阶段和内存线索 |

## ParaView 建议

1. 优先打开 `.pvd`，不要只看某一个 rank 的 `.vtu`。
2. 用 `domain_tag` 区分空气、基座、光栅、PML。
3. 先看 `E_total_abs`，再分别看 `E_total_real/imag`；复数场不能只凭实部判断强弱。
4. MPI 输出已过滤 ghost cell；若自己拼接文件，不能重复计数 ghost 单元。
5. 可用 `python -m src.tools.render_stage4_comsol_views ...` 生成固定视角图，但图只是展示，不代替 JSON 数值 Gate。

## 结果可信顺序

先确认 `ksp_reason>0` 或 direct residual 合格，再确认凝聚/全增广真残差，再读 official RTA，最后看图。`R+T+A_volume≈1` 是功率闭合检查，不是网格收敛证明；不同 h 的结果还要单独比较。

## 常见误读

- `A_balance=1-R-T` 是守恒余量；`A_volume` 是损耗体积分，两者应接近但来源不同。
- probe/Poynting/modal diagnostic 是诊断量；正式 3D Stage 4 使用 DtN auxiliary 模态幅值和体吸收。
- `max_rss_per_rank` 不能代替 `peak_total_rss_including_rta_gb`；工作站容量判断看所有 MPI rank 的总峰值。
- `assemble_only` 目录存在不代表线性方程已求解。

详细字段契约见 [`../reference/code_walkthrough/40_output_schema_and_visualization.md`](../reference/code_walkthrough/40_output_schema_and_visualization.md)。
