# 当前版本边界

更新时间：2026-07-12，Task28 consolidation 分支。

## 已验证

| 项目 | 当前结论 |
|---|---|
| official power source | `dtn_port_modal_amplitudes` |
| absorption | complex material + `A_volume` |
| direct target reference | p=2 h=2 nm |
| condensed operator | exact matrix-free (F-C H^{-1}D) |
| iterative target | p=2 h=5/3/2，MPI4，true residual <= 1e-6 |
| h2 memory | Task028无旧cache clean rerun总峰值13.080 GB |
| ordinary default | 保持既有 direct，不静默切换 |

## 不能宣称

| 项目 | 原因 |
|---|---|
| h=1.5 production solver | 尚未完成同口径残差、RSS和RTA闭环 |
| 严格 mesh-independent | h5/h3/h2 迭代数不单调 |
| 任意参数鲁棒 | 角度、波长、材料与几何扫描未完成 |
| spectral/GenEO成功 | Task027 实验失败 |
| AMS/HX production | 仅FE-only或低阶研究正信号 |
| 最终物理网格收敛 | h2仍是工作站可达参考，不是无限细网格极限 |

## 推荐口径

普通用户使用 direct staged workflow。需要目标 p2 h2 工作站求解时，显式运行 `benchmarks.run_workstation_iterative`，并同时检查 reported、condensed 和 full augmented true residual、总 RSS 与 official R/T/A。
