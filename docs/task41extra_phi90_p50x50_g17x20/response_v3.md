# Task41 P0 Review V3 / V3 执行回应

本回应记录 Review V3 后的 V3 正式尝试、用户批准的 16 GiB 原始证据配额修复，以及保存证据的离线收口。最终 scientific source 为 afbe91e5947ed18fb74d7105097e129c1b8b4cc7；本回应及证据由主控审查并集中提交到同一执行分支，随后等待审阅。

## 1. 范围与身份

| 项目 | 结果 |
|---|---|
| 任务 / 分支 | Task41 P0 B0；task41extra_phi90_p50x50_g17x20 |
| 最终 attempt / service | 20261019T053402.514018Z / myfenics-case-20261019T053359-2096871.service |
| 最终 source | afbe91e5947ed18fb74d7105097e129c1b8b4cc7 |
| terminal classification | WORKER_FAILED；数值分类 NUMERICAL_GATE_FAILED_ROOT_CAUSE_UNRESOLVED |
| official result | false |
| 16 GiB 磁盘配额 | 准入 PASS；投影累计 11,886,541,965 B，小于 17,179,869,184 B；2 GiB free-space 底线仍保留 |
| 固定窗口 | T0 2026-10-19T05:23:07.094241922Z；总窗口 86,400 s，数值窗口 85,200 s，收口 1,200 s；没有重置 |

较早的 20261019T025658.545020Z 记录为 8 GiB 配额不足后的资源门停止：当时预计需要 11,882,448,300 B，旧上限为 8,589,934,592 B，恢复见证未执行。该 attempt 保留为资源停止，不是数值通过或数值失败。当前回应只引用此前保存的运行记录，不重新读取该旧 run。

用户明确批准将 Task41 B0 V3 原始证据配额由 8 GiB 提升至 16 GiB。仅此配额改变；2 GiB 最低剩余空间、内存与 host reserve、swap=0、原数学门和固定窗口语义保持原值。旧合同没有该 policy 时仍保留 8 GiB 默认。相关定向测试已在 [test summary](outcomes/test_summary.md) 记录；此次正式 run 的原始磁盘准入也实际通过。

## 2. 两列 RHS recovery

恢复检查把已知完整场缩减后再恢复，检查恢复场是否仍接近原场；同 LU 校正是在不重新分解矩阵的情况下，用原方程残差修正内部自由度。该检查要求已知 FE 输入的 forward relative error 不超过 1e-11，native volume residual relative 不超过 1e-10；最多允许每列 3 次同 LU 校正。两列初次 forward error 略高于原限值，但初始 native residual 已低于其限值。三次校正后，两列 forward 和 residual 都通过，trace identity 与 slave-zero 也通过。此处只说明保存的恢复见证达到了原门，不把它外推为 full action 通过或定位根因。

| 列 / 模式 | 初次 forward 相对误差 | 初次 native residual 相对值 | 同 LU 校正次数 | 最终 forward 相对误差 | 最终 native residual 相对值 | 门限结果 |
|---|---:|---:|---:|---:|---:|---|
| top / 16030 | 2.0454083899234283e-11 | 3.8000599714433685e-14 | 3 | 8.452404647964512e-14 | 5.198444248297799e-16 | PASS；限值分别 1e-11、1e-10 |
| bottom / 48090 | 2.0406316710458895e-11 | 3.799786706646577e-14 | 3 | 8.462099738746788e-14 | 5.177707803722003e-16 | PASS；限值分别 1e-11、1e-10 |

恢复阶段用尽合同规定的同 LU 修正上限；没有继续增加步数，也没有使用已知误差向量修正结果。恢复 PASS 事件和最终 manifest 的 SHA-256 见 [V3 compact](outcomes/b0_v3_full_action_failure_20261019.json)。

## 3. Full action 门与失败分类

保存的 p6 full-action 输出和 native reduced RHS 均为形状 (5,752,120, 2) 的 complex128 数组，各 184,067,968 B；端口 RHS 为形状 (64,120, 2)，2,051,968 B。两列 D relative error 为 0.0。原 full-action P6/native 门仍为 1e-11，实际误差分别为 3.042118678294192e-10 和 6.391893878204816e-10，因此两列均失败。独立 NumPy 读取已保存向量并按现有 worker 公式重算，得到 3.0421186782950535e-10 和 6.3918938782065652e-10，与记录值仅有约 1e-22 的差异，足以复现超门结论；不以此定位原差异的根因。

| 比较 | top 输入 | bottom 输入 | 原门限 | 结果 |
|---|---:|---:|---:|---|
| 已知输入 RHS recovery，校正后 | 8.452404647964512e-14 | 8.462099738746788e-14 | 1e-11 | PASS，限值是相对误差 |
| 完整 p6 action / native reduced RHS | 3.042118678294192e-10 | 6.391893878204816e-10 | 1e-11 | FAIL，分别超过约 30.4 倍与 63.9 倍 |
| D action 比较 | 0.0 | 0.0 | 1e-11 | PASS |

因此恢复见证与 full action 是两个独立阶段：前者已在原合同内通过，后者未通过。当前证据没有证明差异来自 LU、MPC、映射、复数舍入或某个特定源码路径，根因保持 unresolved。worker 以 exit status 4 报告 full-action gate 失败，service wrapper 以 status 3 退出；run receipt 是 WORKER_FAILED，official_result=false。

## 4. 费用、资源和窗口

| 指标 | 实测 / 派生值 | 口径 |
|---|---:|---|
| 父 workflow | 13,102.74539181916 s | run summary；含各子阶段，不能再叠加子计时 |
| watchdog parent elapsed | 13,102.588685457129 s | watchdog monotonic 计时 |
| 完整 saved surface application | 3,961.9574313424528 s | 子阶段，64,120/64,120 modes；不与父 workflow 相加 |
| process-tree RSS peak | 14,523,883,520 B | process-tree 口径 |
| task cgroup memory peak | 23,537,336,320 B | task cgroup 口径 |
| task swap peak / current | 0 / 0 B | task scoped；后代已清场 |
| resource/time gate | 均未触发 | 本次终止为数值门失败 |
| 固定窗口最终采样余额 | 总计约 72,641.876 s；数值约 71,441.876 s | 以 09:12:25.213291Z 最后 watchdog 样本计，非当前余额 |
| 宿主全局 swap 页面差值 | swapin 177 页、swapout 0 页 | 不能归因到该 task，归因 UNKNOWN |

磁盘准入记录为：已有 artifacts 202,867,440 B，新投影 11,683,674,525 B，累计 11,886,541,965 B；16 GiB 上限为 17,179,869,184 B。准入时文件系统空闲 2,027,809,583,104 B，投影后 2,016,125,908,579 B，超过 2 GiB floor。原 run 已保留全部 141 个 manifest-listed .npy，共 9,379,882,344 B；逐文件大小与 SHA-256 全部匹配 manifest。

旧 V3 三次失败的 watchdog 父成本分别为 1,583.556 s、4,313.646 s、4,320.752 s，共 10217.953 s；与本次 watchdog 父段合计 23320.542 s。仅为已知四次运行父成本，不含未知的全部工程准备/离线核验成本，也不是新窗口重复扣费。全部 source、原始失败和收据 hash 见 [旧尝试费用记录](outcomes/b0_v3_prior_attempt_costs_20261019.json)。

## 5. 离线核验与未运行项

现有 recovery checker 曾尝试直接消费保存的证据，但进程收到 PETSc signal 11，随后 MPI_Abort code 59；没有生成报告。该尝试分类为 INCONCLUSIVE_SIGSEGV，既不是 checker PASS，也不能证明数值实现有错。对已保存的 p6/native RHS 数组，独立 NumPy 读取复现了已有 worker norm 对照并确认两列都超原门限；这只复核比较结果，不替代完整 checker。

本次没有进入 q CSR 或 q factor、KSP/FGMRES、完整场、独立 A6、official R/T/A/A_volume、2 TB 或 48 h qualification。所有这些继续标为 not_run；没有 official field 或 physical output。

主控核对工具原始回执后，发现此前实际有两次 checker 调用，分别使用了错误的 WSL activation 或非合同 JIT 路径。采用与正式运行完全一致的 native activation/JIT/profile 做一次定向复验，complex128/int32 ABI preflight 通过，但 helper 仍出现 signal 11，未写出报告。因此不能把崩溃完全归因于调用路径；其根因仍 UNKNOWN。三次命令/输出和已知工具 wall 成本见 [checker 调用记录](outcomes/b0_v3_offline_checker_invocation_failures.json)，未捕获的第三次完整耗时保持 UNKNOWN。没有重建 FE、重算 carrier 或重启 PDE。

## 6. 决策与下一断点

| 对象 | 结果 / 决策 | 依据 |
|---|---|---|
| 16 GiB 证据配额 | 接受这次用户授权的最小 policy 修复；不据此改变内存或数值门 | 正式 run 的 16 GiB admission PASS，其他原 Gate 保持 |
| Recovery witness | 仅记保存证据的两列恢复门 PASS | 每列最多 3 次同 LU 修正后符合原 recovery 门 |
| Full action | 数值负结果，门未通过；不签发 official result | 两列 p6/native 误差均超过原 1e-11 |
| Offline checker | inconclusive；保留诊断记录，保留三次失败，不再无修复重复调用 | signal 11 / MPI_Abort 59，无输出报告 |
| PDE continuation | 本次不继续 q/factor/KSP/field；待主控审阅失败证据并冻结后续合同 | full-action gate 未通过且根因未定 |
| master / ordinary default | 不合并，不改变 default | 本回应与 V3 research evidence 尚待审阅 |

下一步应由主控先评估保存的 141 个向量和 action/recovery manifest，针对 full action 与 recovery 分离的数值差异提出可证伪诊断；在根因及新合同被审阅、源码身份重新冻结前，不重跑正式 PDE、不降低门限、不增加校正次数。

## 7. 证据入口

- [V3 完整 hash-bound closeout](outcomes/b0_v3_full_action_failure_20261019.json)
- [141 个保存向量的逐文件身份索引](outcomes/b0_v3_saved_vector_hash_index_20261019.json)
- [V3 run index](outcomes/run_index.json)
- [结果总结](outcomes/summary.md)
- [测试和验证边界](outcomes/test_summary.md)
- 远端原始目录：/home/fenics/Projects/laptop_share/results/task41extra_phi90_p50x50_g17x20/task41extra_b0_p6_phi90_07nm_iterative__full3d_iterative__mpi1__Mna/20261019T053402.514018Z

本次收口提交只包含 V3 结果与离线证据索引；运行源码保持冻结，不合并 master。
