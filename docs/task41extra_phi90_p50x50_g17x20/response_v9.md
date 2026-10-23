# Task41extra Response V9：局部筛选改善，完整作用仍未通过

本回应同时执行 Review V9 和准备补充 Review V10。候选 `same_lu_rhs_solve` 对每个内部右端先用已有 LU 求解，再乘同一实际张量的 J，尝试减少预存 T 再乘 RHS 的误差。局部保存数据筛选改善，但完整模型两列作用均未达到原 1e-11 门，不能采用为合格生产路径。没有降低门限、换分母或继续200q。

## 结果与身份

- 分支：`task41extra_phi90_p50x50_g17x20`。
- 本轮最终科学 source / 本文提交前 base：`59722cca5e35eac65efead9fd27f7d7fc0c70419`。
- Review V9：`b24b6ce6577225af7fb03e4a62bef80126efc9b8`。
- 准备 Review V10 完整 SHA：`9e9ecf0e0ee7f658fc7d84e7302d8df936e7ca0f`。
- 正式 run：`20261022T052401.200732Z`；service：`myfenics-case-20261022T052342-2715327.service`。
- 物理仍为0.7 nm、50×50×140 nm域、居中17×20×120 nm Si、方位90°、无额外诊断缺口；28,000个actual键、64,120端口模式。本轮不是完整 Maxwell 解。

| 项目 | 实测结果 | 判定 |
|---|---:|---|
| 局部筛选 col0 自身绝对d | 2.8883352362679107e-9 → 8.305744689149506e-10 | 局部改善，不转授全域 |
| 局部筛选 col1 自身绝对d | 5.708866600426276e-9 → 1.7692662680591898e-9 | 局部改善，不转授全域 |
| 完整col0 动态/冻结相对差 | 2.674977063720297e-10 / 2.6749770637124157e-10 | FAIL，门1e-11 |
| 完整col1 动态/冻结相对差 | 5.613598120037966e-10 / 5.613598120039712e-10 | FAIL，门1e-11 |
| 完整绝对L2差 col0/col1 | 5.953111308801364e-7 / 1.2492954342769817e-6 | 原分母保持 |
| 最大active行 | 两列均87567 | 非旧选中行4766937；原因未闭合 |
| candidate恢复 | NOT_RUN_ACTION_GATE_FAILED | 不转授donor恢复PASS |
| 200q、因子、参考、FGMRES及物理输出 | NOT_RUN | 受完整action门阻断 |

生产 full action 与 reduced RHS 两个 complex128 数组已在判门前保存，各形状[5752120,2]，各184067968 B。没有重跑carrier生成或64,120模式验收扫描；未改端口输出一致。没有完整场、最终精度或2TB/48h通过结论。

## 审核与终止原因

[compact独立审计](outcomes/v9_closeout/task41_p0_b0_v9_compact_independent_check.json)完成，errors为空，重算确认两个action门FAIL；它没有执行新native恢复（调用数0）。这不是checker崩溃。

另一个正式service终态checker未执行：service因 `ValueError: Task41 numerical-output directory is missing` 在该checker之前返回；本run没有合法saved-output snapshot，不用旧run的snapshot替代。此接线缺口与原始数值FAIL分别保留，不能把compact审计冒充正式terminal checker。service退出3、worker退出4；数值失败发生在数值截止前约154秒，不是时间或资源停止。Task41后代已清场。

## 时间与内存

| 口径 | 秒 / 字节 | 范围 |
|---|---:|---|
| run_case完整workflow父段 | 69966.90540991211 s（19.44 h） | 不含所有前期工程准备 |
| fresh volume owner父段 | 68236.865869666 s | 真实start/end事件；约18.95 h |
| donor身份检查 | 183.661680398 s | owner之后 |
| selected incidence | 52.562546269 s | 不等于新最大行归因 |
| col0/col1 action父段 | 165.831110179 / 135.274287935 s | 各自事件区间 |
| 窗口末次launcher累计收费 | 85045.9879224967 s | 含既有准备/失败；不能与workflow相加 |
| sampled process-tree RSS峰值 | 450117619712 B | 约450.12 GB，419.21 GiB |
| watchdog job cgroup峰值 | 450366337024 B | 与RSS不同口径，不相加 |
| systemd MemoryPeak | 449658327040 B | 单独观察值，不取其替代较高峰值 |
| task tree/cgroup swap峰值 | 0 B | 宿主pswpin增加54页，不能称宿主零swap |
| PSS | null / DISABLED_BY_PROFILE | 未采样 |
| 累计科学证据 | 14990282640 B | 小于16GiB；旧负结果未删除 |

J载荷87,091,200,000 B、旧numeric+J约435,653,172,000 B是推导，不能当实际独立backing或RSS节省。GETRS/J/张量生成的独立全域子计时未完整记录，保持UNKNOWN；不能把整个owner父段都归给Gram或GETRS。未计量的历史准备费用保留UNKNOWN。旧service命名、C source绑定和prefix注册失败保留，不伪装数值通过。

固定窗口T0为2026-10-22T01:12:42.209257168Z，数值截止2026-10-23T00:52:42.209257168Z，总截止01:12:42.209257168Z；没有刷新。cap 1.5TiB、host reserve64GiB、MPI1/math1、原ABI和数值门未变。

## 保存成果、验证和下一断点

原始目录（工作站）：
`/home/fenics/Projects/laptop_share/results/task41extra_phi90_p50x50_g17x20/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261022T052401.200732Z/`

原样小型记录：[action audit](outcomes/v9_closeout/task41_p0_b0_v9_compact_volume_audit.json)、[独立audit](outcomes/v9_closeout/task41_p0_b0_v9_compact_independent_check.json)、[run summary](outcomes/v9_closeout/run_summary.json)、[service receipt](outcomes/v9_closeout/task41_p0_service_receipt.json)。完整向量路径/bytes/hash见action audit；这些大数组不进入Git。

最后相关源码回归为prefix注册5 passed/38 deselected/1.04 s；此前C source绑定9项、准备14项等沿原准备记录保留。此次收口只核JSON、hash、文档差异，不重跑数值或全仓测试，不声称CI通过。

下一审阅应先复用已保存完整S作用/reduced RHS及原donor，按原尺度分块定位新最大行87567及全部incident贡献，区分局部改善未推广、累加/算子差和RHS差；是否需要补极少数同身份局部块由证据决定。终态checker应支持保存的数值FAIL而不要求成功物理输出目录。以上是待审建议，不自动执行第二候选、全域重建或200q。
