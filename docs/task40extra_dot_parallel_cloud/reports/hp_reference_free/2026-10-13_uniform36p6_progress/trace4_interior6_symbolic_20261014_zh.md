# trace4_interior6_symbolic_20261014

日期：2026-10-14（UTC）。范围：同一 native 108 单元、fine p6 问题上的新 trace-p4 + interior-p6 粗空间；本报告记录源码资格、两次实际 symbolic 阶段和终态核验。

## 结论

第二次实际运行完成新映射、完整稀疏 K、独立体积/DtN/投影动作检查及全新 MUMPS JOB1，并按计划停止在全局数值分解之前。第一次在旧 p4 条件图上限处正确拒绝。两次均已结束且进程清理通过。

已纠正的是“新精确浮点支撑图仍可用旧 p4 的 4,996,864 上限”这一记账假设。测得 entity-external 微小支撑尾部，但这些数据不能证明它们导致旧 Maxwell/BAL_H 平台。没有得到 108 单元或 hp 收敛结果。

第二次实际运行的独立终态复核已完成，状态：ACTUAL_MAP_GRAPH_K_COMPONENTS_AND_JOB1_PASS_CLEAN_STOP_NO_NUMERIC

## 1. 空间与未变更的物理问题

- 保持同一 108 单元 fine p6、原 native 算子、完整原 80 个端口。
- 新场空间为 10,224 个 trace-p4 活跃自由度，加全部 48,600 个 fine-p6 单元泡函数，场 FE 维数 58,824；计入端口后 58,904。
- 场嵌入为 diag(Pt,I48600)，保留变量嵌入为 diag(Pt,I80)，新的 Schur K 为 10,304 × 10,304。Pt 为 23,976 × 10,224。
- 原 p4 范围按该构造包含；实际方向、MPC、共享行、局部秩及 P/Pᴴ 的三次语义探测通过。有限探测不等于所有 RHS 或完整 PC 的证明。
- 任意非零 interior RHS 的消去/恢复、完整粗解及完整 BAL_H 仍待下一实际阶段。没有用低阶因子替代新 K。

## 2. 源码资格与第一次受控失败

core_v4 的 45 项、entry_v1 的 40 项 stdlib/源码测试通过；这些只给出源码资格。此前候选的清理/所有权及薄入口缺陷已在冻结版本中修正，不把新候选中的缺陷归因到旧平台。

第一次实际运行（core_v4 / entry_v1）：

- 用时 59.907065382 s；235 个资源采样；进程树采样峰值 1,616,130,048 B。
- 实际 16 个缓存角色、单一 fine 凝聚所有者及实际 P/Pᴴ 门槛通过。
- 在 volume/cell/55 的精确支撑并集增长时触及条件上限 4,996,864，抛出“projected support exceeds admitted ceiling before insertion”。
- 子进程 exit 1；AIJ K 分配、新 K/组件动作核验和 JOB1 均未到达。没有将失败当作数值结果。
- 原监督器确认清理完成、无剩余进程；不是资源监督器强停，也未做进程内重试。

## 3. 仅修正图记账，再做第二次实际运行

core_v5 / entry_v2 的窄范围源码复核与 77 项 stdlib 测试通过。精确图改用固定 10,304 × 10,304 位图：每行 161 个 uint64，载荷 13,271,552 B；以位并集表达精确去重；未发现旧版本重复计数缺陷。另有独立 64 MiB 工作区准入。完整图先输出标量收据，随后按实际 nnz 重新准入 AIJ，位图在该时点仍计入存活集。

此更改保留全部浮点非零系数，不做阈值、截断或重缩放；不改 P/Pᴴ、体积或端口系数，不放宽任何原资源限制。Pt 哈希与第一次完全相同：

`131167d5770521d4b869c054040047a7f08cbeb58b96a780b60f8976ca726695`

第二次实际结果：

- 用时 113.541041724 s；448 个资源采样；进程树采样峰值 1,845,731,328 B。
- 子进程 exit 0；清理验证通过、无剩余进程。
- Pt 的精确 nnz 为 1,532,520；三次 P/Pᴴ 语义检查最大相对误差 2.7823761102479465e-16。
- 完整 K 图 nnz 为 10,646,336；原 80 端口保留；没有完整全局稠密 Q，也没有构造全局 fine S6。
- K CSR 内容哈希：`9546bcbaf88712cbca0e545c441a17faa462fa0a866cc84bb64f53be3fd84c99`。

## 4. 微小支撑尾部：观察成立，因果尚未成立

诊断以实际最小 fine 实体、同一 coarse 实体闭包及实际 primal MPC 展开定义允许列，在精确合并后的同一行上统计，不修改系数。

active 实际 Pt 中 entity-external 项有 1,092,841 个；最大绝对值 5.328512817041033e-15；其 Frobenius 平方占比为 1.2339844848576127e-29。它们能使“精确非零支撑”明显变大，不能据此断言物理注入错误，也不能解释旧 Maxwell 平台的成因。

slave 的合并后、提取前统计单独保存：209,853 个外部项，最大 4.7351929265065995e-15，Frobenius 平方占比 1.576349024958078e-29；未与 active Pt 混用分母。

## 5. 实际动作检查与 JOB1 的严格边界

三个单位归一化探测中，独立 native 体积、DtN、K 对 native S6、完整贡献检查均低于 1e-10。最大相对误差分别为：

- native 体积：3.4492821137645562e-15
- native DtN：2.9581455941150393e-16
- 投影 K 对 native S6：5.8119354573436860e-16
- 完整贡献：2.4218464453886655e-16

独立拆分检查避免体积与 DtN 误差互相抵消。这里是动作资格，不是任意 RHS 粗解、预条件器或收敛资格。

全新 MUMPS 仅执行 JOB1：预计因子项 29,224,384；symbolic 内存估计 832 MB；原 sizing 公式给出未来请求 1,675 MB（十进制 MB）。分析句柄已销毁。全局数值分解、全局 solve、PC、CG 和 outer 迭代计数均为 0，未创建 outer KSP。fine 局部 LU 确实发生，不能写成“没有任何分解”。

## 6. 资源、清理与完整成本

原限制保持：硬 RLIMIT_AS 6 GiB、整棵进程树 8 GiB、host available 至少 1 GiB、系统和进程零 swap、每次 600 s、磁盘余量至少 4 GiB、总新输出 128 MiB、MPI1/thread1、单一科学子进程，无 OOC。

未来数值因子与 H3/场向量/诊断/余量的命名增量为 2,931,985,088 B；另计 875,348,032 B 持久 ELF 预留，因此当次准入增量为 3,807,333,120 B，预计整树为 5,824,072,448 B。原守卫在该时点确实检查 current VmSize + 2,931,985,088 B < 6 GiB；额外 ELF 预留进入 tree 口径，5,824,072,448 B 不是 AS 数值。通过准入不是漏查 AS。保存的收据没有精确 VmSize 数值或余量，不能重建该余量，也不能把当次准入说成未来 numeric + H3 + PC 已实际可行。

两次实际尝试都计入成本：合计 173.448107106 s；两次采样树峰值的最大值为 1,845,731,328 B，不把分时峰值相加。准备、源码复核和等待时间未测量，不记为零。RSS 为采样峰值，不代表未采样瞬时峰值的精确值。

独立终态复核核对全部 448 个资源采样、2,699 次准入和 16 个缓存调用，均通过；swap 与换入换出增量为零。日志存在 hwloc CPU topology sysfs 警告及 UCX /sys/class/net 发现错误，不能写成无警告。实际 MPI1/thread1、UCX_TLS=self 阶段 exit 0，MUMPS INFOG(1)=0，未见这些环境告警对已核验标量结果的致命影响。

已知所有者清理与监督器进程终态验证成立；不声称原始 helper 隐藏的每个部分构造 native 句柄都有单独显式销毁收据。

## 7. 下一步与结论限制

下一步仅为 numeric + H3 + 同一冻结 6656 输入的 PC 诊断做源码准备，仍须独立源码/生命周期/完整存活集检查及下一阶段授权。实际任意 interior RHS、粗 solve、全 native Qᴴ 残差、eps1/eps2 和完整 BAL_H 检查尚待进行。

本报告不能宣称新 PC 更有效、未来分解一定装得下、108 单元收敛、hp 收敛，或已经找到旧 BAL_H 平台的唯一原因。

## 8. 证据索引

随附 JSON 只含有界标量、状态和 SHA-256；未上传源码、矩阵、向量、张量、因子或缓存。证据根标签为 hp_resume_20261013；下列相对路径用于对应原始收据，并不声称这些原始大文件已公开发布。

- `phase4_trace4_interior6_candidate/core_v5/core_v5_qualification.md`（3237 B）：`1addeb037fd3196e5cdd32c836a30928b0ce29ce1fbe5a905f56e048132389d2`
- `phase4_trace4_interior6_candidate/entry_v2/launch/resource_ledger.md`（8603 B）：`758f3d0a481260de9e4a3ed6027772ef920038684c23dee353945535d4949d30`
- `phase4_trace4_interior6_source_review.json`（31214 B）：`81efbd7582e3b33d6fae3311e2fa4201f13519c9fcb26d3354e7a8293c37e911`
- `phase4_trace4_interior6_entry_source_review.json`（24483 B）：`0db4f4f7b9672e6bb025470f25776e7c3b4317acc7473053b97c7be1e6b0759f`
- `phase4_trace4_interior6_v5_entry_v2_source_review.json`（20058 B）：`9b3f8659498f71792926da2e74b44a545addd78cfc7de57d0e53694986af4003`
- `phase4_trace4_interior6_symbolic_attempt01/summary.json`（1175 B）：`a65cb79d85b67987040077effe9b6f416e1951d9dadd75bb063148f651f43509`
- `phase4_trace4_interior6_symbolic_attempt01/failure.json`（357 B）：`a173c2cdfef7c4059cfcd71ccb352bb23b74a2f2d248d11f491a6775222c59e3`
- `phase4_trace4_interior6_symbolic_attempt01_terminal_review.json`（21124 B）：`de3406ec5a91e8e7ca00c79652789ceef23ecd9f26fe18c33ceebfea361749e9`
- `phase4_trace4_interior6_symbolic_attempt02/summary.json`（1178 B）：`5b5d92c57fbb6defe49f75b9430495a9be4873562bc0329d8460521eba167e18`
- `phase4_trace4_interior6_symbolic_attempt02/result.json`（213962 B）：`b4b90eaa30ed801d12d6134d6a3ab26f6bb04f6e65f02b0e5a797cf33ab28228`
- `phase4_trace4_interior6_symbolic_attempt02_terminal_review.json`（40474 B）：`4f85c1e65c58b35b087ce5c9fda29273c35be6f87c6474444d68bf91bdd63cc6`
