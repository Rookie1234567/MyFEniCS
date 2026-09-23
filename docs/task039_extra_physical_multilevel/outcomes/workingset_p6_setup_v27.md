# V27 working-set / p6 setup：工程配对收口（无正式求解结果）

## 结论

R1 最终完成了六组同工作集算子配对：i=16 的 A6、H6 来自 attempt03，i=16 的 BAL_H 及 i=112 的 A6、H6、BAL_H 来自获准的一次 attempt04 重放。各组均通过 `1e-10` 数值等价门；所有记录的 R2/V26 配对输出差为 0。受控结论为 `NO_REPRODUCED_IMPLEMENTATION_REGRESSION`：这些工程短操作没有复现历史 V26 全 KSP 相对 r2 慢约 18.9% 的差异。但它们不是完整 KSP，不能据此证明所有迭代、供电或系统态效应都不存在。

attempt03 在 BAL_H 第一次应用前因探针把 `InterfaceBalancedCoupling.apply(source)` 错按双参数接口调用而退出；这属于工程适配器错误，不是数值失败。用户随后明确允许一次定向 bug replay。attempt04 修正副本探针并重建一次 p4 factor/p6 工作集，补齐余下四组配对；不再启动重放或正式 PDE。

R2=`NO_ADOPTED_CHANGE`：保留 r2 为速度基线，ordinary default 不变。R4 fresh formal p6/h7.5 solve=`NOT_RUN`。本批没有新 Krylov 迭代、true residual、场、R/T/A 或 formal memory 结论。

## 六组算子配对

每个操作将历史运行保存的残差向量送入两个预条件器/算子路径，按 AB/BA/AB 顺序各测三次，比较输出并记录计时；这不是让求解器从该步继续迭代。V26/R2 为 wall-time 中位数之比，小于 1 表示该小样本中 V26 较快。

| 已保存向量步数 | 操作 | R2 / V26 中位 wall（s） | V26/R2 | 输出/等价门 | 原始证据 SHA256 |
|---:|---|---:|---:|---|---|
| 16 | A6 | 3.252565 / 3.243044 | 0.997073 | 每组输出差 0；相对独立 native A6 为 6.7113e-15 | `7ced34db…7cbe` |
| 16 | H6 | 4.000405 / 3.976555 | 0.994038 | 每组输出差 0；通过 `1e-10` | `c5c99b02…6020` |
| 16 | BAL_H | 18.734961 / 18.635279 | 0.994679 | 每组输出差 0；通过 `1e-10` | `7295a18a…7f29` |
| 112 | A6 | 3.254658 / 3.260999 | 1.001948 | 每组输出差 0；相对 native A6 为 6.1633e-15 | `56fa5316…4dfa` |
| 112 | H6 | 3.845772 / 3.762207 | 0.978271 | 每组输出差 0；通过 `1e-10` | `351077a9…0f3f` |
| 112 | BAL_H | 16.927638 / 17.181086 | 1.014972 | 每组输出差 0；通过 `1e-10` | `8243d575…6daa` |

BAL_H 每次逻辑应用调用两次 p4 `MatSolve`，没有触发额外 residual-refinement solve。最大原始 A4 相对残差：i=16 为 `9.167487524231193e-12`，i=112 为 `6.470229892354096e-12`，均低于 `1e-10`。完整 warmup、三次 wall/CPU 数值、顺序、输出身份和计数保存在上述原始 JSON，机器 compact 记录也绑定其 SHA。

i=16 BAL_H 的 R2 wall trials 为 `[18.734961328, 18.958400222, 16.717120448] s`，V26 为 `[22.574130732, 18.635278850, 16.535293970] s`；首个 V26 样本偏高，且两侧随轮次都变快。i=112 BAL_H 的对应三次为 R2 `[18.148221484, 16.927638002, 15.966040178] s`、V26 `[19.448918716, 17.181086410, 16.070105096] s`，两侧同样逐轮变快。AC1 采样为 online；电源模式、CPU 频率和 threadpool inventory 未知，因此不把时差归因于某一供电因素，也不声称已排除全部机器状态影响。

载入向量范数分别为 `||r16||=0.0059228472836568066`、`||r112||=3.879261627632226e-6`。它们只是已有 V26 运行中 hash-bound 残差向量的输入范数，不是本批重新求解得到的残差。对照而言，历史 V25 Q4 p4/original h7.5 的 i=112 显式真残差为 `2.71399585136905e-6`、记录累计 solve time `3437.2333360950015 s`、该 checkpoint RSS/PSS=`7384477696/7352336384 B`、swap=0；这是历史基线，不能替代 V27 formal result，见 [V25 Q4 记录](records/a6_h6_coarse_degree_v25_q4.json)。

## setup 成本、内存与边界

两次进入实际 setup 的 attempt 各建立一次 p4 factor 和 p6 cache；计时字段严格按边界分开。builder audit 是 setup 内部子项，不应与 setup 相加。

| 指标 | attempt03 | attempt04 | 两次同口径合计 |
|---|---:|---:|---:|
| p4 numeric factor | 213.987342 s | 223.155029 s | 437.142371 s |
| p6 setup internal total | 255.476535 s | 249.130047 s | 504.606582 s |
| p6 outer retained-setup wrapper | 255.485893 s | 249.145521 s | 504.631413 s |
| builder audit（嵌套子阶段） | 249.919023 s | 242.479440 s | 492.398462 s |
| builder kernel（audit 主项） | 237.094091 s | 228.841967 s | — |

每次 p4 为 84680 rows、32320342 NNZ，`ICNTL(23)=4687` decimal MB，factorization 时 solve-call=0。attempt04 p6 kernel 占 builder audit 的 94.3758%，local Schur 为 11.954928 s；共有 12 类 raw tensor、26 类方向 Schur，numeric cache 为 325283184 B，identity 矩阵只读共享、唯一存储 1.62 MB。

与 V26 旧记录比较时只对齐相同计时字段：V26 `p6_build_seconds=259.023949 s`、kernel `244.655193 s`。attempt03 builder/kernel 的描述性差值为 -9.104926 s（-3.5151%）/-7.561102 s（-3.0905%）；attempt04 为 -16.544510 s（-6.3872%）/-15.813226 s（-6.4635%）。这是未配对、不同运行的一次性 setup 计时，不构成因果加速证据。尤其不能把 V27 retained-setup wrapper 时间直接与 V26 builder 时间比较。

| 资源口径 | attempt03 | attempt04 |
|---|---:|---:|
| watchdog elapsed | 723.646801 s | 966.853607 s |
| simultaneous process-tree RSS peak | 7132229632 B | 7148744704 B |
| 同一采样树 PSS peak | 7100228608 B（从 1402 条 timeline 重算） | 7116825600 B（从 1861 条 timeline 重算） |
| process-tree swap peak | 0 B | 0 B |

这只是 engineering worker 生命周期的同时进程树观测：当时保留一个 p4 factor、p6 cache、ports/work vectors 和两侧 candidate actions；没有完整正式 FGMRES basis/history，不能当作 production 单候选求解的内存峰值或排除 solver-history 内存影响。attempt01 未进入 worker；attempt02 在 FE setup 前结束，watchdog 2.022931 s。attempt02–04 可量化 watchdog 时间合计 1692.523339 s，不含无 outer-wall 记录的 attempt01；不把它误称为全部桌面等待时间。

## 决策、来源与后续

R2 审计没有发现同一 material/geometry class 被大规模重复做昂贵 tensor 构造：12 个 class 各只有一份活动 raw kernel，26 个方向 Schur；已按唯一 class 做本地表格化。主耗时仍是精确 FFCx kernel，尚无证明保持物理/局部校验不变且能降低此项的低风险实现。因此不再追加 JIT/backend 或其他猜测性优化；下一研究点仅登记为 same-integral exact local tensor tabulation，不默认采用。

attempt04 的 launch source identity 为 HEAD `bb541cf3286b89734181d1da1a0ecfd2a5078243`、dirty tracked diff SHA256 `1d9a5283c57acce7453baf52466e1d062a0bb8c8afcb905497800023cc41fb69`、source-state SHA1 `665a8528ac0ab0937189b40f254e6ca844c8b095`、probe SHA256 `3b81385fe019dfb31d758325129b85abd70f2807e39af6b4eb19b50ae1be7d4b`。因此该测量不绑定到之后的文档提交或干净 HEAD。attempt04 watchdog/raw paths 位于 [attempt04](../../../benchmarks/artifacts/task39extra/workingset_p6_setup_v27/r1_attempt_20260923_04)，i=16 A6/H6 的复用原始 pair 位于 [attempt03](../../../benchmarks/artifacts/task39extra/workingset_p6_setup_v27/r1_attempt_20260923_03)。权威紧凑入口为 [combined pair](records/workingset_p6_setup_v27_pair.json)、[selection](records/workingset_p6_setup_v27_selection.json)、[compact](records/workingset_p6_setup_v27_compact.json)、[decision](records/workingset_p6_setup_v27_decision.json) 和 [run index](records/run_index.json)。

qualified WSL activation 下 ABI preflight PASS（PETSc complex128/int32）；五文件 focused suite=`47 passed in 8.29 s`，三文件 documentation contracts=`21 passed in 0.07 s`。JSON/hash/link 与 diff check 在本次记录检查中通过；commit/push 状态以最终 Git 核验为准。full repository pytest、Ruff、CI、温度/频率 qualification、正式 PDE 与 formal FGMRES memory 均未运行/未取得。
