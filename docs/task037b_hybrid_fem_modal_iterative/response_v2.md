# Task037b Review V1 response v2：R1–R5 research closeout

## 结论先行

本轮把“完整端部求解器”理解为：先用精确的 Matrix-free action 描述端部方程，再测试
一组不形成全局直接矩阵的局部近似逆。它的收益目标是降低内存，代价是必须用重新计算的
true residual 证明近似确实有效。

R1 证明了真实 DtN 分解 action；R4 证明了 exact F inverse 加 40-mode Woodbury correction
与 complete A 一致。R5 在同一冻结配置下的 PC 代数、线性、确定性、K、数组有限性、factor
lifecycle 和资源 Gate 均通过，但 21 个非零 RHS 的 capacity 为 0/21，正式结论是
WHOLE_ENDCAP_ILU0_DTN_WOODBURY_NEGATIVE。该结论只否定本任务冻结的 local inverse
candidate，不否定 Hybrid 模型，也不表示 Woodbury 公式失败。

## R0–R5 状态

| 阶段 | 结果 | 边界 |
|---|---|---|
| R0 | pass | source、authority、qualified ABI 和 ordinary default 边界冻结 |
| R1 | pass | F/C/D/H action decomposition；bottom/top 各 6 probes |
| R2 | complete controlled negative | 六-slab F-only 未达到 true-residual Gate |
| R3 | complete controlled negative | whole-endcap ILU(0) 的 F-only 与 complete-A 均未资格化 |
| R4 | pass | exact F inverse Woodbury 与 exact A 一致，公式/符号/ownership 正确 |
| R5 | numerical negative | 合法 PC 但 21/21 非零 RHS 失败；正式停止 |

R5 random residual 约 6.89e-3–9.56e-3，modal 约 4.87e-5–2.04e-4，top physical
约 8.19e-4。severe_negative=false 只表示没有触发预定义 severe 子标签；它既不满足
full，也不满足 borderline，因此按 Review V1 §13 仍归 negative。

## 正式身份与资源

| 项目 | 值 |
|---|---|
| source | 2a2ef3d37514e4ab30d50209065af84c1dafd59b |
| branch | codex/20260807-task37b-hybrid-iterative-development |
| frozen case | p6/h10、modal p6/h10、M120/candidate240、MPI8、S、10°、10/110 nm |
| numerical path | static-condensed、full3d_uniform_cg、scalar_cg_discrete_derivative |
| R5 process-tree peak | 6432.54296875 MiB = 6.281780242919922 GiB |
| R5 resource threshold | 7.0 GiB；standalone review only |
| worker RSS peak | 6417.9296875 MiB |
| swap / warning / termination | 0 / false / false |
| total wall | 735.0470628660405 s |
| H6 eligibility | false；R5 numerical Gate 未通过 |

低于 7.0 GiB 只说明本轮 standalone resource measurement 通过，不是 H9 或 production
resource qualification。R5 official R/T/A、field 和 12+12 没有运行。

## 开发与合入边界

ordinary defaults unchanged。Hybrid-P、低秩 direct Hybrid 与本 iterative candidate 都是
research-only，不得称为 production-qualified。H5 原始负结果、response_v1、review_report_v1
和 task.md 未改写。H5c、H6、H7、H8、H9、H10 均 not_run，并因前置数值停止保持 closed
pending new review；本回应不自动提出扫描、调参或新候选。master merge not authorized。

## 证据索引

| 证据 | 位置 |
|---|---|
| 五阶段 compact hash-bound record | [Case101 record](../../benchmarks/cases/101_hybrid_iterative_block_solver/records/task037b_v1_r1_r5_research_closeout_v1.json) |
| R1–R5 逐 RHS 与解释 | [local endcap evidence](outcomes/local_endcap_inverse_matrix.md) |
| R1–R5 资源 | [resource ledger](outcomes/resource_ledger.md) |
| 测试与静态 Gate | [test summary](outcomes/test_summary.md) |
| source chain | [changed files](outcomes/changed_files.md) |
| Case101 scope | [Case101 README](../../benchmarks/cases/101_hybrid_iterative_block_solver/README.md) |

本 docs closeout 不运行 full pytest、CI、PDE 或 MPI，不改变任何源码和阈值。
