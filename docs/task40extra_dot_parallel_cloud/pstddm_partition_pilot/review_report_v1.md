# PSTDDM pilot V1：独立静态准入审查

日期：2026-11-11 UTC。结论：**APPROVED_BOUNDED_P2_EXPERIMENT**，仅批准下面四项既定 p2 小试验进入运行时资源门；不是数值通过、物理精度通过或合并批准。

本次方法将远处激励的作用逐层改写为相邻层的源，再组合局部场。审查重点是这些源有没有重复或遗漏、是否仍在解同一个全局方程，以及局部计算连同辅助工作是否留在原预算内。审查没有启动或重跑原生 PDE。

## 范围和运行顺序

| 顺序 | 输入 | 目的与边界 |
|---|---|---|
| 1 | `check_p2.dat` | 非零 FE/aux 制造载荷，检查原生映射、弱截断、重构及同系统直接参考 |
| 2 | `direct_p2.dat` | 固定 0.7 nm、120 hex、p2 原 Floquet–DtN 系统的 fresh direct reference |
| 3 | `candidate_p2_n2.dat` | N=2 两层端点计源和原算子对照；不期待此全域特例节省内存 |
| 4 | `candidate_p2_n4.dat` | 同一全局模型上的局部 PML 源转移与 FGMRES；允许保存受控负结果 |

输入实际文件名以 `input/pstddm_partition_pilot/` 中已审文件为准。每次只能有一个正式 PDE，启动前由执行方确认没有其他 heavy case。必须先提交本轮源码和文档并满足 clean branch gate，再运行。p4、p6、目标规模、其他分区或 PML 参数扫描均不在此次准入范围。

结构、映射、ABI、原算子身份或资源 gate 失败时，不得当作算法通过；先保存失败证据。仅外迭代未在 100 步内收敛可以作为有界负结果保留，不能通过放宽阈值、改变损耗或删除端口制造通过。接口修复和重试仍计入用户规定的总次数与时间预算，并绑定新源码身份。

## 数学与代码检查

| 项目 | 静态结论 |
|---|---|
| 真正源转移 | 新核心不调用全局残差更新 `r -= A delta`。正反向各有独立累计源、相邻双层局部逆、逐层重构，与旧 Schwarz 型双扫有实质区别 |
| 符号与计源 | 对正号 Maxwell 弱算子，正向包含原源截断项和负 commutator；反向内层不重复添加当前原源，最低端点单独添加原源；N=2 特例和多层代数 oracle 覆盖计数 |
| H(curl) 截断 | 使用场的弱 curl 乘积式，未以 edge DOF 乘标量代替。原生检查另组装直接 UFL 乘积表达式与 commutator 比较 |
| 任意残差 | 先精确消去 aux 残差，再用原全局质量矩阵做 Riesz lifting，验证各层弱源之和回到输入残差；输出端口由原辅助方程恢复 |
| Orientation/Floquet | 原生入口按物理 cell 检查 orientation，并验证 `Tl S = T`，包含 slaves/corners；N=2 另验证映射后的局部算子为原 `A-CD` |
| 连续重构 | 逐层局部场组合后做原空间 L2 投影，保证结果属于原 H(curl)/Floquet 空间。它仍是离散近似，不宣称一次双扫代数恒等 |
| 全局物理身份 | 原全局材料、双 Floquet、836 个有序 DtN 模式和原 RHS 保持不变。PML 仅用于人工局部切面，真实端点保留原 DtN |
| 参考与验收 | direct 原 full residual 至多 1e-10；candidate full residual 至多 1e-8，物理总 E/H 复场 L2 相对误差分别至多 1e-4/1e-3。另保存散射场误差和诊断功率比较 |
| 制造源证据 | 物理 RHS 与制造 RHS 分开保存；制造 raw FE/aux RHS、原 MPC 数组、已知解及直接/候选误差保留，可独立回读原方程 |
| 小测试边界 | 已审七项代数测试及执行记录，包括复数可变预条件 FGMRES、非零初值、跨 restart 和步数受限负例。这不是原生 FE/PML 数值资格；后者仍待实际运行 |

## 资源与身份门

监督器已拒绝优化模式，启动前持久登记 case/time reservation，未完成登记阻止继续；保存 UTC、输入和源码哈希，结束后检查 HEAD、tracked/staged/untracked 状态及字节身份。

- MPI1，线程数固定为 1，一次一个进程组；每案至多 1800 秒，总数至多 10，总数值时间至多 21600 秒，不自动扩大。
- 100 ms 采样进程组及监督器；RSS 加独立 512 MiB 余量小于 2 GiB；阶段前还计入计划工作集。全局质量因子和全部局部因子实际同时驻留，不能遗漏。
- 系统可用内存维持 2.5 GiB 底线，系统用量及前瞻余量在 6 GiB 内；零 swap，并检查系统 swap 计数不变。
- 磁盘保留 12 GiB 底线及 256 MiB 输出余量。运行时输出限 240 MiB，为监督记录留 16 MiB；最终全部输出包含 JIT、日志和监督记录，总量不得达到 256 MiB。
- 超限或异常终止所属进程组，TERM 后轮询，必要时 KILL，并检查没有残留。最终证据必须检查真实退出原因，不能仅以进程退出码 0 当数值通过。

这是一套保守的前瞻门和采样监督，**不是已经验证的内核硬内存配额**；4 n²×16 字节只是因子工作集计划量。N=4 中间局部问题预计有 4560 independent rows、4080 PEC-free rows，可能因现场 RSS 被拒绝，不能据此扩大预算。

## 已审最终代码身份

| 文件 | SHA256 |
|---|---|
| `src/solvers/pstddm_source_transfer.py` | `6d56be199cef1698952bfbf004d6955b171ffc95f702791420757ed882b55648` |
| `src/solvers/pstddm_native.py` | `97efd8543ae3fde2f16a780811c673bed2ca749712e0833a321a759a8010cf71` |
| `src/solvers/pstddm_comparison.py` | `a484bdcc0b8938d96e995fc0c77c267e4769c985a52ccdf9135a60886e0da4f8` |
| `src/runners/pstddm_case.py` | `e0aca37ec6ef11001d27d66ed1bf86a049d56856e7b5095cddd0e177c5e4b7fd` |
| `benchmarks/pstddm_partition_pilot/supervise.py` | `f2e6a662692218f0394b603f0deb4c07e307f44c52e1e3321389cdd9f37f3e22` |

每次正式运行仍须记录实际完整 source SHA；以上内容哈希不能替代提交身份。GitHub rendered view 待提交后核验，不冒称已完成。

## 结果解释和下一次独立回读

此极小模型的 PML 开销可能使 N=4 局部问题大于原全局 FE 系统，且保留全部局部因子和一个全局质量因子，因此不能预先声称内存下降或完全取消全局分解。必须比较整个 case 的实测峰值、全过程时间、局部次数、外迭代和参考场误差。

运行后从保存的原 A/C/D、T、MPC、真实 RHS、质量/curl Gram、背景交叉项和全复解独立重算原投影方程、端口方程、约束、E/H 误差及资源门。未资格的功率/吸收后处理只能作为 diagnostic；同离散通过不等于网格、DtN 截断或真实物理精度收敛。

方法背景见 [Du/Wu 原 PSTDDM](https://arxiv.org/html/1505.06052v4) 和 [2025 Maxwell STDDM](https://link.springer.com/article/10.1007/s10915-025-02872-7)。前者的标量结构和后者公开摘要不能直接证明当前非均匀 Floquet–DtN 离散收敛；本审查没有声称读到后者的订阅正文。
