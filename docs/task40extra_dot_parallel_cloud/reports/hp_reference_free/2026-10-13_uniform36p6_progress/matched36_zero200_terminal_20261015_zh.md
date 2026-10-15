# matched36 中层单段从零 200 步终态报告

日期：2026-10-15 UTC。本报告收口新 `6×2×3`、36 单元的准备、capture、唯一一次 BAL_H 从零 200 步试验及独立复核，接续[matched108 终态报告](matched108_zero200_terminal_20261015_zh.md)。波长 0.7 nm，fine p6 / coarse p4、H3、FGMRES restart 32、CGS refine always，hard 600 s。

## 结论与对照边界

新 36 跑满 200 步后，完整原 FE 相对残差仍为 `0.3958855744981088`，约为 RHS 尺度的 39.6%。KSP reason −3（迭代上限），随后原严格精度门拒收、child exit 1；资源和清理通过。没有合格场、official R/T/A 或新方法成功，也没有继续数值运行的许可。

相对于 matched108，新 36 保持完全相同的 exact x/y 坐标，只把 z 中层的 7 段改为 1 段，三层总计由 9 段变为 3 段；物理域与物理设置保持。其结果明显更差。但 z 分段也同时改变 fine/coarse 空间、DoF 和谱，不能把差异单独归因为单元长宽比，也不能把更少单元当作更容易求解的保证。BAL_H 的失效根因仍未建立。

## matched36 与 matched108 的主要比较

retained-native 是凝聚后保留未知量上的原 native 作用；saved Ax 是独立对保存的矩阵、右端与迭代向量重算；完整 FE 是原 producer 恢复内部未知量后应用完整原算子的诊断。本次审计独立重算 saved Ax，没有重新装配 FE。三者均用各自 RHS norm 归一化，未跨组拼接分母。

| 指标 | 新 matched36，6×2×3 | matched108，6×2×9 |
| --- | ---: | ---: |
| 初值与迭代设置 | zero / 32 / always / 200 | zero / 32 / always / 200 |
| fine / coarse 独立 FE DoF | 24192 / 7296 | 70848 / 21120 |
| fine / coarse trace 加 80 辅助行 | 8072 / 3488 | 22328 / 9536 |
| retained-native 相对残差 measured | 3.9588557450e−1 | 1.4134196775e−4 |
| 独立 saved Ax 相对残差 measured | 3.9588557449e−1 | 1.4134198674e−4 |
| 完整原 FE 相对残差 measured | 3.9588557450e−1 | 1.4134196689e−4 |
| 完整 FE RHS norm measured | 1.0821612412946005 | 1.0821612412946005 |
| 当前严格门 | 未通过 | 未通过 |

当前严格门为 retained-native ≤1e−11、saved ≤1e−9；历史 full FE 门为 1e−6。本次三者均未通过。原 132 的从零 200 步 full FE 为 `9.8393763517e−7`，仅通过历史 1e−6 门；旧 `18×2×3` 108 为 `2.2054730773e−2`。它们使用 refine never，不能作为当前 always 设置的严格单变量对照；旧 108 的 RHS norm 也不同。精确值、各自分母与来源身份见[配套 JSON](matched36_zero200_terminal_20261015.json)。

旧 36 仅作背景：它是 warm 初值、fresh global SuperLU 预条件的 FGMRES 一步结果，fine raw 使用 rounded 6 类；本次为 zero、BAL_H/p4、fine exact 15 类。旧 x[5]=2.1648148148148145 nm，本次为2.164814814814815 nm，相差 1 ULP。旧 saved residual `4.6472434495e−12` 不能证明本次 BAL_H 路径收敛；即便矩阵行数和 nnz 一样，也不能据此认定矩阵相同。

## 实际下降过程与诊断门

| 步数 | retained-native 相对残差 measured | 独立 saved Ax 相对残差 measured |
| --- | ---: | ---: |
| 64 | 0.39614963851896823 | 0.3961496385152574 |
| 128 | 0.3959105936810352 | 0.3959105936776783 |
| 192 | 0.3958855867563925 | 0.39588558675260005 |
| 200 | 0.39588557449661277 | 0.3958855744930093 |

四点的独立 saved Ax 与 producer 记录在原容差内一致。到 64 步后下降已很小，200 步仍远离接受门；这条曲线不等于已定位具体代码 bug。

32 次 recovery identity 检查通过，终值 `3.2024152437045415e−11 < 1e−10`；31 个正步端口门通过，终值 `4.525640299502113e−16`。iteration 0 的原相对端口值仍为 1、相对门失败，其分子与尺度都约 `8.486951425576565e−30` 且端口解为零；该零尺度边界保留，不改写成所有端口门通过。

200 次外层 PC 调用对应 402 次逻辑 coarse solve；另有 139 次 repair，共 541 次实际 Mat solve。最大 coarse native relative 为 `9.98959970456711e−11`，各次均通过原 1e−10 门。matched108 的 repair 为 14 次；这是成本和行为差异，尚不足以证明停滞因果。

## 准备与资源成本

实际映射确认 fine 为 15 raw / 24 oriented exact 类，p4 为 6 raw / 12 oriented rounded 类。21 类 raw 中沿用 14 类同上下文种子，新建 7 类（5 fine、2 p4）；只声明同已资格化 C kernel 的有限值与类型/来源身份，不声称每个新输入分别完成 O0 等价性验证。

capture 得到 8072 阶 A，nnz=5886416，小于结构上界7077376；CSR 与 b 文件118207461 B，全部 regular 产物119157984 B。文件身份/NPY头由独审流式核验；finite 与全部 stored-entry union 包含性来自已审 producer 的完整检查，未由报告编写重新计算。

| 阶段或成本项 | 时间 秒 | 采样树峰 RSS 字节 | 口径 |
| --- | ---: | ---: | --- |
| 实际 map | 3.766782467 | 291717120 | 监督 wall |
| raw 单批补齐 | 199.056347390 | 128360448 | 监督 wall |
| capture | 30.963388385 | 1247096832 | 监督 wall |
| solver | 195.158662234 | 1340538880 | 监督 wall，含构建、求解、清理 |
| 本次四阶段合计 | 428.945180476 | 不可相加 | 已知监督 wall 之和 |
| BAL_H build | 51.909028141 | 不单列 | 已包含在 solver wall |
| KSP solve | 128.571065845 | 不单列 | 已包含在 solver wall |
| 其中 PC apply | 60.791049570 | 不单列 | 已包含在 KSP solve |
| 独立四点 saved Ax | 6.574557324 | 不混用 | 单列审计成本，不计入上述科学 wall |

7 类新 raw kernel 共193.159564585 s，嵌于raw wall；终态完整native诊断1.976868726 s，嵌于solver wall。不得重复累加。map内部另有293277696 B快照，高于外部采样峰；采样峰不代表连续完整峰值。

solver 的772个外部资源样本、294次内部admission全部复核，零swap、无残余进程。AS 6 GiB、树RSS 8 GiB、hard600及host/disk限制未改变。fresh p4 MUMPS INFOG16/17均为84 decimal MB，按原规则选择ICNTL23=179 decimal MB。solver compiler cache调用17次，capture为13次，二者不混算；solver fine/p4 raw命中15/6次，raw kernel与cold compiler均为0。

原worker仅原子更新latest checkpoint；64/128/192/200的完整向量由父进程只读复制保存，副本及metadata/manifest合计524509 B，独立四点Ax及身份齐全。复制用时未独立记录，不记为零，也不授予场接受或续算资格。

v96总账已保留旧失败与中断：已知terminal科学阶段和25294.360433219015 s，含旧中断的已知下界33429.79364659202 s。二者都不是端到端项目wall；工程准备、审查等待与复制成本不为零，但没有完整可核时钟，不能补造总耗时。

## 证据与发布范围

- 最终solver独审：`ed03a110c37b4a2fc9cee1c6d6d86b5f0f2b79c4e495180cbd4941b6b35d65c3`
- 独立saved Ax：`e9776c8febac8603c0fec6ea2fac2f2ddf9acca05b40bf81b3ee9f40b8e94054`
- capture独审：`e33bedc815cb43cbd2463f8b84e42e459524deb71b2a0a940663b6debe4b1340`
- v96总账：`9637d436e9442011adeab4e356fc1583478e7fc7066e2b218d55e1a217ef30c0`

配套JSON保留其余小证据SHA，不公开私有执行路径。仅发布中文报告和小scalar JSON，无代码、数组、矩阵、因子或归档。JSON与表格列数已检查；connector发布、精确文件读回与远端HEAD另留回执，不声称canonical工作树、GitHub rendered-view或CI Gate通过。
