# 原生迁移与容量任务：本轮执行结果

| 范围 / 阶段 | 状态 | 主要证据 |
|---|---|---|
| R0 native环境与隔离 | NATIVE_ENVIRONMENT_PASS | [环境与硬件](environment_and_migration.md)、[ABI](records/native_abi.json) |
| R1 attempt1，13.5 nm Si p6/h10，MPI1 | 身份检查失败，未outer | [原始负结果](records/r1_attempt1.json) |
| R1 retry1，同一模型 | PERFORMANCE_CONTROLLED_STOP；筛选未通过 | [复现/阶段资源](reproduction_13p5nm.md)、[完整compact](records/r1_attempt2.json) |
| R2 notch、条件native reference | NOT_RUN_BY_PREVIOUS_GATE | 无完整场/衍射/能量资格 |
| S5 / S3 / S2 / G | NOT_RUN_BY_PREVIOUS_GATE | [容量边界](capacity_frontier.md) |
| 性能修复 | 局部等价性通过，完整PDE尚未重新资格化 | `f124679e75915758076d9240bd4bef2f5c772752`；[测试](test_summary.md) |

## 最新正式 original run（attempt3）

本次是用户授权后的 clean-SHA、zero-start formal retry；旧 attempt1/attempt2 仍作为历史失败保留，未被覆盖。run compact：[records/r1_attempt3.json](records/r1_attempt3.json)。

| 项目 | measured 结果 |
|---|---|
| source / run | `9b1e8d4a1b2be9fca5b126a1ec3893e3af295e5e` / `20260909T130326.291096Z` |
| lifecycle | `exit=0`、`COMPLETED`、`descendants_cleared=true`、workflow `12560.042750451947 s` |
| numerical Gate | iteration `550`，true `9.998974191134654e-7`，solve `11589.4608165932 s`，outer `567` matvec / `550` PC |
| checker | `independent_output_gates_passed=true`，`gate_failures=[]` |
| authority | `BALANCED_OUTPUT_AUTHORITY_LIMITED`; `WSL_FULL_FIELD_COMPARISON_PARTIAL`，不是完整 R1 |
| field/modal evidence | 80 通道 relative amplitude difference `1.339354498931458e-9`；own R/T/A 与能量记录已保存 |
| p4 assembly | `491.016220843 s` vs old `1818.610 s`，`3.703767661438x`，降低 `73.000466%` |
| final enclosing-tree resources | RSS peak `3631751168 B`，swap peak `0`，watchdog samples `36437` |
| release lifecycle | RSS before=`3078565888 B`，after=`3078565888 B`，delta `0 B`；不声称发生 OS/allocator 回收 |

阶段资源峰值也已在 compact 中逐项保存：setup `3404267520 B`、solve `3085901824 B`、recovery/final peak `3631751168 B`、checker `3558637568 B`、complete `3202437120 B`，均 swap `0`。绑核证据只说明 CPU23/CPU9 affinity，不推出共享内存带宽或功耗无竞争。

因此 R1 的 own 数值/物理输出通过，但完整场资格仍关闭；不重跑 550 步、不启动 notch。下一步是既有 native direct matched reference 的 symbolic preflight 与最小接线审计，之后再由主控审核是否需要源码改动。

本轮仍使用原V5 BAL_H + accurate global p4 LU，没有新迭代算法、子域法或预条件器。worker独占逻辑CPU23、监督器CPU9，隔壁CPU0–7进程未修改；缓存、venv、Git、结果全部属于独立worktree。共享socket的缓存/带宽不可能仅凭绑核证明完全零影响，未作这类承诺。

## 正式结果（measured；GiB=2^30 B）

| 模型 / attempt | p6 storage / independent | p4增广rows / NNZ / factor NNZ | outer / fine true | p4 worst true | workflow / s | 同期RSS峰值 / GiB | swap |
|---|---|---|---|---|---:|---:|---:|
| 13.5 nm Si p6h10 / 1 | 173802 / 164592 | 53164 / 24730144 / 53417584 | 未运行 | 未运行 | 2731.775 | 2.787 | 0 |
| 13.5 nm Si p6h10 / 2 | 173802 / 164592 | 53164 / 24730144 / 53417584 | 62 / 0.019433158954790204 | 4.893382586118271e-11，124次，修正0 | 3997.651 | 3.163 | 0 |

两次均无official R/T/A/A_volume、R00_s/R00_p/R00_total、80通道复幅值或selected E/H。它们是“未取得”，不是零。第二次完整true尚未达到1e-6；screen同时未满足0.01或足够完整周期趋势，不能因曲线继续下降而越过筛选。第32步native/WSL完整残差绝对差3.13e-13支持当前迭代轨迹一致，但不替代场/能量Gate。

## 已查明的性能问题与解决范围

| 问题 | 已实现处理 / measured效果 | 尚未证明 |
|---|---|---|
| 初次parent与worker抢CPU8 | parent9、worker23分离 | 与隔壁零共享带宽影响 |
| p4生成内核跨行访问、寄存器spill | 独立元素改按行访问；真实单元CSR装配6.935→1.929 s，逐位一致 | 完整252单元正式装配时长；约8.2分钟只是预测 |
| curl内核重复扫描独立系数 | 合并12个独立循环，原生成C单元p6约2倍、p4约1.4倍；真实FE逐位一致 | 完整外迭代加速倍数及R1通过 |
| PSS逐次读取增加开销 | RSS安全采样保留、PSS降频；单次采样约0.09→0.034 s | 大容量case监督开销 |
| 释放后RSS未显著下降 | 完整记录释放前后3.0787/3.0745 GB和最终清场 | 未证明allocator具体滞留或回收改进 |

物理矩阵、载荷、积分、复数精度及Gate均未改变。CPU23实测约3.6GHz；CPU2的外部限频/内存90°C是另一个已记录硬件异常，本轮没有解决它，也没有绕过热保护。变慢的可修复内核和监督开销已有实证；不能把诊断提速当正式求解成功。

## 身份、边界与下一步

base为`450255f4575792d052c1bac29837d39955ee1039`；R1 retry1运行SHA为`b2e132a7b1f1078eb3359c87a336123b3c7dfbdd`，input SHA为`eb18ecd70d49cccb1564c8c3a93d8f89d25b8734ff448b16929de5d65fd273b9`，physical SHA为`9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`。运行前后clean source与全部hash见compact。历史移交提交`72a0f58899dc5d98aa4c170edffb573ed50067c7`只读使用，没有向task39extra/task41/master写入本任务结果。

任务书§11要求screen/solve性能失败后停止主阶梯，不能把该负结果当迁移bug重复抽签。本轮交付状态为fail / PERFORMANCE_CONTROLLED_STOP；性能修复作为可审阅的显式native实现保留，额外formal retry须有明确例外授权。当前没有最短own-pass波长、没有精度资格或G网格一致性结论。具体后续blocker是单核生成内核成本与原screen预算之间的矛盾，不是开发新PC的授权。

两次formal累计wall约6729.43 s；先前准备、测试及诊断另有分项日志。尚未构造覆盖整个会话每条命令的完整campaign计费总表，不声称已完成该项完整记账；所有已知计算远低于864000 s总上限。性能诊断是同机单核小测试，不把人工等待或并行诊断父子时间重复叠加为formal wall。

## Selective merge建议

| 依赖组 | 内容 | 建议 |
|---|---|---|
| production core / numerical | native模式身份桥、严格浮点FFCx调度模块和显式接线 | 数学等价小测试通过；完整R1未重新资格化，暂不提升普通默认或合入master |
| reusable runner/watchdog | native隔离、RSS/PSS降频、身份异常分类 | 定向进程/MPI测试通过；与profile一起审阅 |
| checker/benchmark | native比较器、性能/模式/监督测试 | 依赖对应实现；不从compact状态直接推导成功 |
| compact evidence/docs | 本目录outcomes、response、总账和progress | 可独立审查正负证据，保留旧失败 |
| research-only | 本次native容量profile、CPU硬件/内核诊断 | 未资格化完整PDE；保持显式opt-in |
| do-not-merge | results、benchmarks/artifacts、tmp、venv、JIT/C/SO/矩阵/场 | ignored；只提交必要hash索引 |

未获merge approval，不合并master。证据入口：[response](../response_v1.md)、[运行索引](records/run_index.json)、[测试](test_summary.md)。
