# 003：2D TE/TM 与复材料吸收

| 契约字段 | 固定内容 |
|---|---|
| 1. ID | `003_2d_te_tm_complex_absorption` |
| 2. 证明 | TM/TE 复材料真实求解满足 residual、非负 R/T/A、体吸收与端口闭合 |
| 3. 不证明 | TE 与 TM 数值应相同，或材料数据对特定实验准确 |
| 4. 物理问题 | 2D 周期端口复材料 |
| 5. 几何 | TM：100/100/50 nm；TE：10/5/5 nm，完整值冻结在各 record |
| 6. 材料 | Si 示例 `0.999002304859+0.00182649365j` |
| 7. 波长/角度/偏振 | 13.5 nm；TM 0 度，TE 15 度；分别冻结 |
| 8. 边界 | x-Floquet；TM DtN 或 TE Robin/DtN |
| 9. FE/网格 | TM N1curl p2/h3；TE Lagrange p1/h2 |
| 10. PyCharm preset | `2d_complex_absorption`, `2d_te_port_smoke` |
| 11. 参数表 | [`config.json`](config.json)、两个 record 的 `resolved_config` |
| 12. 精确命令 | `sh benchmarks/cases/003_2d_te_tm_complex_absorption/run.sh` |
| 13. 调用链 | run_cases -> solve_port_maxwell/solve_te_maxwell -> power_metrics |
| 14. 理论 | Maxwell TM/TE 与 official RTA 理论 |
| 15. 求解器 | serial manual direct |
| 16. RTA 恒等式 | `A_balance≈A_volume`，`R+T+A_volume≈1` |
| 17. 输出 | complex config、分区 absorption、R/T/A |
| 18. Gates | parser complex；positive Im(eps)；residual；absorption identity |
| 19. Canonical 结果 | TM/TE closure `3.33e-15/5.83e-16`，详情见下表 |
| 20. Records | [`records/tm_complex_absorption.json`](records/tm_complex_absorption.json)、[`records/te_complex_absorption.json`](records/te_complex_absorption.json) |
| 21. Artifact 规则 | `benchmarks/artifacts/cases/003/` ignored |
| 22. 限制 | 两个偏振是独立 frozen variants；外部 n 数据必须先统一时间谐波符号 |

## 物理问题

本 case 冻结两个互补 variant。TM 使用较大 EUV 周期和多衍射阶 auxiliary DtN，检验 complex beta 与 auxiliary/trace；TE 使用小平层标量 DtN，检验独立 TE admittance。它们不要求几何相同，也不用于比较 TE/TM 数值大小。

## 参数说明

两者都使用 `n=0.999002304859+0.00182649365j`，配置按 `epsilon_r=n^2` 得到正虚部吸收。TM 为 N1curl p2/h3、30 auxiliary DoF；TE 为 Lagrange p1/h2、explicit zero order。resolved config 完整保存在 record，可复现性以该字段而非 README 摘要为准。

## PyCharm

TM 可用 `2d_complex_absorption` preset。TE 交互入口 `2d_te_port_smoke` 需要把 substrate/grating index 改成同一复数；canonical 复现建议建立 Module 配置 `benchmarks.run_2d_canonical`，分别传 `--case 003 --variant tm` 和 `--variant te`。

## CLI 或测试

```text
sh benchmarks/cases/003_2d_te_tm_complex_absorption/run.sh
python benchmarks/check_benchmarks.py --no-write
```

完整场和 solver log 写入 ignored artifact；轻量 records 才进入 Git。

## 代码路径与理论

TM 走 `solve_port_maxwell::run_port_case -> compute_dtn_auxiliary_power_metrics`；TE 走 `solve_te_maxwell::run_te_port_case -> compute_te_dtn_port_power_metrics`。两者都通过 `power_metrics::_volume_absorption_metrics` 得到 independent `A_volume`。

有损端口规则见 [`../../../notes/theory/official_and_diagnostic_rta_methods.md`](../../../notes/theory/official_and_diagnostic_rta_methods.md)。

## 当前证据

| 指标 | TM | TE |
|---|---:|---:|
| FE + aux DoF | 14,452 + 30 | 56 + 0 |
| residual | 3.323e-14 | 1.486e-15 |
| peak RSS/MB | 365.30 | 287.48 |
| R | 3.6625e-6 | 8.7456e-5 |
| T | 0.8821724521 | 0.9903457798 |
| A_volume | 0.1178238854 | 0.0095667639 |
| closure | -3.331e-15 | 5.829e-16 |

TM auxiliary/trace 最大差 `1.221e-15`。probe closure 分别约 `-0.0213` 和 `0.0751`，明确为 diagnostic_only。

## 结果解释

official Gate 使用实际端口平面 coefficient，因此基座传播衰减只计算一次。phase-normalized report amplitude 不参与功率。probe 偏差不会覆盖端口/体积分闭合。

## 限制

这两份记录验证有损功率口径和离散求解，不证明材料数据库实验准确、near-Rayleigh 鲁棒性或跨网格收敛。
