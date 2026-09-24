# Review V27：V29 A4 / p6 tensor / H6 收口

## 结论

在 original 模型、p6/h7.5、p4 粗层、990 个六面体单元、80 个 DtN 端口模态、MPI1/thread1 下，唯一正式 V29 运行完成 126 次外层迭代。端口 DtN（在有限计算区域边界表示外部传播/衰减波）和内部吸收检查通过；独立重算的完整 A6 真残差为 `9.283162362107749e-7`，释放后仍相同，限值 `1e-6`。结果为 `DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED`：它证明这一个离散模型的一致性，不代表连续极限收敛、其他波长或其他几何也通过。

与 V28 修复后同网格比较的完整 FE 度量、同坐标 E/H 与切向界面场、80 个复模态幅值及逐模态/合计功率全部通过。worker 原有 reference 字段仍是 `NOT_ATTEMPTED`；独立离线对照单独绑定，不改写 worker 原始 authority。

## 分块计时、资源与原始尺度

setup 是准备空间、端口、矩阵/因子及预条件器；KSP 是迭代解算；后处理包含独立终态核验、释放检查和物理输出。每个时间只按自己记录的边界解释，嵌套计时不能相加成另一种“总耗时”。monotonic 是单调时钟；conservative realtime 是按真实经过时间保守记账。V29 两者相差 `221.208 s`，原因 unknown，不分摊给任何阶段。

| 区段 | 本次 V29 实测 | V28 同边界比较 | 解释/内存对象 |
|---|---:|---:|---|
| Setup | monotonic `533.755 s`；conservative realtime `582.442 s` | monotonic `773.946 s` | 观测少 `240.191 s`（31.03%）；输入/网格/端口/JIT、p4 因子与 p6 局部缓存均在本次 run 生命周期内。该阶段 realtime 与 monotonic 相差 `48.688 s`，未定位原因。 |
| KSP.solve only | monotonic `1837.175 s` | `2113.443 s` | 观测少 `276.268 s`（13.07%）。不含 KSP setup、terminal residual snapshot，也不含 outer adapter 保存/校验；outer adapter 自身 `1852.369 s`，不能与 KSP 相加。 |
| 最终原 A6 核验 | monotonic `5.751 s` | — | 完整原算子显式重算最终残差。 |
| release 检查 | monotonic `11.461 s` | — | 释放后的身份/数值检查。 |
| 官方后处理 | monotonic `15.164 s`；conservative realtime `18.144 s` | — | 正式 DtN 模态和材料体积吸收，不采用诊断 Fourier 结果替代。 |
| 完整 wrapper workflow | monotonic `2422.426 s`；conservative realtime `2643.635 s` | monotonic `2936.076 s` | 同口径观测短 `513.650 s`（17.49%）；只有一对运行，不能据此断言某单项造成全流程加速。 |
| 峰值内存 | worker 进程树 RSS/PSS `7,323,303,936 / 7,291,101,184 B`（1176 样本）；watchdog 树 RSS `7,326,449,664 B`（8993 样本） | V28 watchdog 树 RSS/PSS `7,356,289,024 / 7,324,145,664 B` | 两场 swap 均为0、子进程均清空。观察到的 RSS/PSS 较低不是资格化内存收益；采样数不同。worker 与 watchdog 口径分列。 |

运行维度为 p6 `667152` full rows（`644760` independent rows）、p4 `201520` rows、990 cells；单进程单线程；PETSc complex128/int32；MUMPS 后端、排序/主元/BLR/OOC 与线程策略均保持原设置。本轮没有创建第二张 p4 全局矩阵或第二个全局因子。

### Setup / KSP / 后处理分项计数

完整 p4 粗层修正是在 p4 上解内部块，再用端口 Schur 接口补回边界；A4 是独立执行完整粗层算子检验返回结果，不是只看凝聚矩阵的误差。本轮原有的每次 A4 完整检查一项未少。

| 分项 | 次数 | 累计墙钟 | 边界说明 |
|---|---:|---:|---|
| p4 logical units / physical F4 / MatSolve | `262 / 267 / 267` | `243.563 s` p4 整体 | reduce `76.480 s`、solve `94.275 s`、recover `72.433 s`；父子计时是同一段拆分，不额外相加到 workflow。 |
| A4 完整正向检验 | `267` | `159.091 s` | `fused_sum_factorized_partial_assembly_full_A4`；与同 p4 form/DtN 的原生 FFCx 身份 oracle 对照；所有 logical call 都执行。 |
| BAL_H / H6 / 外层迭代 | BAL_H `131`（setup1、迭代126、检查4）；H6 `131`；KSP `126` | BAL_H A-structure `529.874 s`、C `557.432 s`、smoother `525.036 s` | 这些是可能重叠的操作桶，不相加成总耗时。KSP `129` matvec。 |
| A6 候选内部动作 | 正式 PC 内次数见原 worker ledger | 内含于 solver 生命周期 | operation bucket 有嵌套；不与上列项或 workflow 相加。 |
| 释放/终态/后处理 | 各见上表 | `5.751 / 11.461 / 15.164 s` monotonic | 保持独立阶段记录。 |

正式 A4 计数按 setup/iteration/check 分别为 `2/253/12`，实际 MatSolve 同样 `2/253/12`，合计 `267`。总逻辑单位 `262` 中发生 `5` 次额外精化（iteration 1、check 4）；这些修正均未让粗层目标超限。所有 126 次外层迭代都执行完整 A4 检验，没有隔 N 次检查或抽样省略。

### Setup 对象、局部构建与分阶段内存

有限元单元凝聚可以直观理解为：先在每个单元里解完内部自由度，只把邻接单元共享边界与端口留给全局问题；最后用保留的局部解恢复内部场。p4 还需要一个全局接口因子；p6 这里只缓存每类局部张量/Schur，不形成 p6 全局矩阵。

这里将 p4 与 p6 的局部构建记录分开：`26.588 s` 和约 `17 MB` 暂存属于 p4 接口凝聚，不是 p6；p6 的实际构建审计为 `34.122 s`，原始张量暂存约 `149 MB`。两组数值来自同一 worker summary 的不同 JSON 节点，不能互相代替。

| 对象/阶段 | 时间或计数 | 内存/维数口径 | 边界 |
|---|---:|---:|---|
| 完整 setup 窗口 | monotonic `533.755 s`，conservative realtime `582.442 s` | 完整窗口边界内的 RSS/PSS 峰值 `unknown`；worker 仅有 phase 标签为 setup 的早期4个样本，RSS/PSS 最大`1,041,850,368/1,009,605,632 B` | 这4个样本不是完整 setup 窗口峰值；完整窗口还包括组装前准备及后续阶段，不以 setup 标签样本代替。 |
| p4接口矩阵与MUMPS因子 | 84680 rows；symbolic `0.637 s`、numeric `216.394 s`；所属interface setup累计`250.099 s` | MUMPS INFOG19 allocated `4,688,000,000 B`、INFOG22 used `4,327,000,000 B`；ICNTL23读回4687 MB | MUMPS内部计数，不是整树RSS/PSS；interface setup包含本项及周边操作。 |
| p4局部raw tensor/接口凝聚 | 12类；total build `26.588 s`；kernel max-rank `23.561 s`；局部插入max-rank`0.747 s`；局部Schur max-rank`0.315 s`；trace preallocation`0.859 s` | raw tensor最大暂存`17,280,000 B`、oriented Schur暂存`15,335,424 B`；retained numeric cache最大`24,541,920 B`；identity cache 26类/`2,426,112 B` | 原始字段为 `.interface_stack.condensation`；p4局部LU/map独立计时未记录。raw/kernel/Schur为嵌套字段，不能相加。 |
| p6局部raw tensor/Schur | 12类；total build `34.122 s`；kernel max-rank `20.289 s`；局部Schur max-rank `11.552 s`；单元张量维数882 | raw tensor最大暂存`149,361,408 B`、oriented Schur暂存`77,635,584 B`；retained numeric cache最大`325,283,184 B`；候选workspace上界`40,600,224 B`；本rank identity cache 1类/`1,620,000 B` | 原始字段为 `.operator_identity.retained_p6.p6_build_audit`；全局p6矩阵未物化。候选workspace是门控上界，不与暂存或RSS相加。 |
| H6构建 | diagonal `4.799 s`、power10 `39.087 s`、positive selected action `0.488 s`、B6 shell `0.000671 s` | 局部缓存见worker audit | 是H6 setup子项，不另加到setup窗口。 |
| factor阶段 | worker树RSS/PSS峰值`6,945,210,368/6,913,007,616 B`（25样本） | sampled v29q4 inventory peak`6,508,502,382 B`；workspace peak`1,167,956,936 B` | inventory/workspace是对象与工作区台账，不等于RSS，也不可加到PSS。 |
| solve阶段 | worker树RSS/PSS峰值`7,323,303,936/7,291,101,184 B`（1137样本） | inventory peak`6,554,231,494 B`；workspace peak`1,167,956,936 B`，workspace live peak`1,056,456,352 B` | 全流程最高worker进程树峰值；watchdog全树另有8993次采样。 |
| 组装阶段 | worker树RSS/PSS峰值`1,912,086,528/1,879,872,512 B`（5样本） | inventory peak`1,174,973,030 B`；workspace peak`76,405,680 B` | — |
| Evaluation / cleanup | Evaluation RSS/PSS=`7,315,034,112/7,282,828,288 B`（3样本）；cleanup=`7,306,645,504/7,274,439,680 B`（1样本） | inventory peak均`6,554,231,494 B`；cleanup inventory used为0 | 清理样本数有限，不能解释为释放前后同口径峰值差。 |
| Preflight阶段 | worker树RSS/PSS=`430,845,952/397,787,136 B`（2样本） | inventory/workspace均为0 | — |

Review V27要求同一正式阶段分别给出 monotonic、保守 realtime 与 CPU 时间。保留的 worker/watchdog 记录没有按阶段 CPU 计时，因此 preflight、完整 setup、p4 factor、p4/p6局部构建、H6 setup、assembly、factor、KSP、最终残差核验、release 后核验、官方后处理与 cleanup 的 CPU 秒数均为 `unknown`；不从 wall-clock 推算。逐项 unknown 与所绑定源文件见组件及 compact JSON。

空间/约束/端口/JIT 的独立准备耗时、bridge/startup 检查耗时及正交化耗时也没有单独记录，wall seconds 均为 `unknown`；不从父阶段或每步累计桶中拆分、重算。

| 在线操作桶 | 次数 | 累计 (s) | 每次均值 (s) |
|---|---:|---:|---:|
| A6 live action | 263 | 517.156 | 1.966 |
| H6 apply | 131 | 525.036 | 4.008 |
| P | 263 | 77.895 | 0.296 |
| PH | 269 | 69.326 | 0.258 |
| 完整 A4 验算 | 267 | 159.091 | 0.596 |
| p4 F4 粗层求解 | 267 | 243.563 | 0.912 |

上述动作桶跨越共同的BAL_H/KSP生命周期并有部分嵌套，不能相加替代纯KSP或全workflow时间。完整逐阶段字段、RSS/PSS、inventory/workspace与每项的原始哈希见[组件账本](records/a4_tensor_h6_v29_components.json)。

工程失败成本也单独保留：A4 保存序列化失败已知发生，但本次可审查目录没有绑定该尝试的raw identity和elapsed，故均为unknown，不计入成功配对中位数。P3 attempt01因为FFCx积分组不匹配、attempt02因default cell integrals未资格化而失败；两个partial JSON及SHA在组件账本中，原记录均没有 elapsed 字段，因此成本unknown。H6 attempt01另因adapter缺 `_live_kernel` 失败，monotonic/realtime=`52.606/58.515 s`；修复后的attempt02精确等价但apply较慢。以上工程失败不是正式PDE的数值失败，也没有被删掉或折算成通过。

## 数值与 V28 同步检查点

下表 residual 是 full explicit true residual，elapsed 是 monitor 记录的 `solve_seconds`；二者逐 checkpoint 都来自相应原始 monitor JSONL。Δ 为 V29 减 V28。每步残差差仅约 `1e-12`，耗时则是这两场机器状态下的实测差，不能单独归因某个 kernel。

正式监控的残差每8步、场快照每32步策略维持原样；本表只抽取用户指定的每16步比较点，没有减少正式记录频率。

| 外层步 | V29 真残差 | V28 真残差 | V29 elapsed (s) | V28 elapsed (s) | Δ耗时 (s) |
|---:|---:|---:|---:|---:|---:|
| 16 | 4.143722297496328e-3 | 4.143722296393416e-3 | 259.863 | 307.741 | -47.879 |
| 32 | 3.352917963022611e-4 | 3.352917960283653e-4 | 523.708 | 631.303 | -107.594 |
| 48 | 1.941922131412018e-4 | 1.941922139532232e-4 | 767.970 | 925.579 | -157.609 |
| 64 | 3.023352328679727e-5 | 3.023352344552171e-5 | 1030.517 | 1216.850 | -186.333 |
| 80 | 1.760946846839249e-5 | 1.760946879795428e-5 | 1275.831 | 1491.888 | -216.057 |
| 96 | 3.776699947905199e-6 | 3.776699911513131e-6 | 1537.185 | 1782.623 | -245.438 |
| 112 | 2.713995401371934e-6 | 2.713995819640953e-6 | 1783.358 | 2057.739 | -274.381 |

i=112 已记录的 V28 p4 基线有两个核验项：`2.311786751695389e-11` 用时 `0.883030884 s`，以及精化后的 `4.019658502559789e-13` 用时 `0.828502759 s`；该同一步进程树 RSS/PSS=`7,351,422,976 / 7,319,279,616 B`，swap0。两项都保留，不把一个冒充另一个；不存在的 baseline 项不补造。

## P1–P4 候选结果与工程成本

| 项目 | 实测/门限 | 决定 |
|---|---|---|
| P1 有界精化后继续外层 | 最多两次额外精化；formal coarse-target-unmet 为 `0/262`，故“超限后选最佳有限状态继续”仅由小 fixture 覆盖 | 采用到本 profile；没有声称正式场触发了软返回；NaN/Inf、因子错误、外层 breakdown 与资源安全 Gate 仍是硬错误。 |
| P2 完整 A4 | 12 个保存状态、每状态3次；native/candidate median `1.662441/0.589996 s`，约 `2.818x`；完整作用最大相对差 `3.18e-12`、原 RHS 残差差 `3.18e-12` | 采用；没有减少 A4 频率，没有构造 global p4 matrix/factor。 |
| P3 p6 raw tensor | 12/12 类型通过；所有类型 native/candidate `230.547/19.558 s`，比值0.08483；矩阵/Schur/恢复最大差分别 `1.97e-15/1.23e-14/1.72e-12` | 采用到本 profile；本地矩阵生成候选不更改 p4 solve/factor 输入。仅为本次12类资格，不是所有材料/网格通用保证。 |
| P4 H6 实虚批处理 | i120 输出差0；apply `3.893095/3.958853 s`，候选慢1.69%；setup `44.966/44.551 s` | 不采用。setup 微小下降不足以抵消在线 apply 变慢。 |

H6 attempt01 在执行候选前因适配器引用不存在的 `_live_kernel` 失败，monotonic `52.606 s`、保守 realtime `58.515 s`；attempt02 修正适配引用后完成等价性与速度测量，候选仍退出。P3 配对总历时 `254.817 s`，P4 attempt02 `124.478 s`；这些 engineering wall clocks 不是额外正式 PDE 时间，也不能拼入正式 workflow。原有 R1 部分运行按用户选择保留且不重放：已知 p4 factor/p6 setup 完成、A6/H6 检查通过，BAL_H/i112 缺项继续标为缺失；它不与本次正式 V29 合并，且未在本记录重建其 raw hash/耗时。

本轮依赖组与合入先后另见 [Selective merge manifest V29](selective_merge_manifest_v29.md)；它仅供审阅，不构成 merge approval。

## 官方物理量与证据边界

官方 DtN 端口结果为 `R_total=0.36509755369517294`、`R00_s=0.36506086288159717`、`R00_p=4.8132151055651866e-23`、`R00_total=0.36506086288159717`、`T_total=0.013016803348172958`、`A_balance=0.621885642956654`、`A_volume=0.6218856421420225`。端口吸收与体积吸收差约 `8.15e-10`，能量闭合误差 `-8.15e-10`。80个 DtN 通道均通过内部有限性、功率与归一检查。

V28 同离散离线检查：FE L2/scaled-curl 相对差 `1.6170e-11/1.6155e-11`；同坐标 E/H 及界面切向场最大相对差 `3.37e-10`；复模态幅值相对差 `1.4542e-11`；最大逐模态功率绝对差 `5.9471e-11`；R/T/A/A_volume 最大合计差 `8.1122e-12`。限值分别为 `1e-4/1e-4/1e-4/1e-6/1e-5`。完整离线 audit 状态 PASS，明确未启动 PDE、物理算子、因子或 KSP。

正式 worker 的 `reference_evaluation.attempted=false` 原样保留；离线同场比较是补充证据，不回填 worker 的 reference authority。所有完整场、矩阵、因子与时间线继续留在 ignored raw root；轻量 hash 和结果摘要见[compact](records/a4_tensor_h6_v29_compact.json)、[checker](records/a4_tensor_h6_v29_checker.json)、[组件记录](records/a4_tensor_h6_v29_components.json)、[精化策略](records/a4_tensor_h6_v29_refinement_policy.json)与[选择记录](records/a4_tensor_h6_v29_selection.json)。
