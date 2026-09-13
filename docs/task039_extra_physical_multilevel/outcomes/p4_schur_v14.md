# 当前 V14/V15 数值与资源结果：Q1/Q2 完成，Q3 未准入

本次按用户“先不考虑时间gate，继续推进看看”的授权，使用显式 `--v14-time-policy observe_only` 完成了可准入的 Q0→Q1/Q2→Q3→Q6。结论分别是：**准确 Schur 精度通过但没有省内存；固定接口近似在三份真实 p4 输入上均失败；original/notch 因 Q3 不准入而未运行。** Q6 的 `Q6_FINALIZED` 只表示负结果及证据完成汇总，不是完整 PC 或物理通过。下方历史快照保留原停止事实，不代表当前执行状态。

准确 Schur 是先解并消去 42 个宏块内部未知量，再解共享接口，最后恢复完整场；本例宏块覆盖 252 个六面体单元。它重写同一个方程，减少接口行数也会增加消元填充和耦合存储，收益必须用全部因子、装配转换和恢复的成本衡量。Q3 将全局接口分解换成一次固定的局部修正—小粗修正—局部修正，直接替换整个旧 I4；没有叠加旧 C_U/S-p2、四步内层、recycling 或新增路线。参考仅作评价。

## 当前阶段与源码身份

| 阶段 | 精确 source SHA | 实际结果 |
|---|---|---|
| fresh Q0 attempt 3 | `6a8b273c383d5bd9da37d6630a48bd24d6a90cce` | worker `Q0_CORE_PASS`，独立/存储 p4 行 48960/53084，内部/接口 35868/13092，42 块全覆盖、跨内部 owner 连接为零。 |
| Q1 原 p4 LU → Q2 准确 Schur | `6a8b273c383d5bd9da37d6630a48bd24d6a90cce` | 两场均准确性与资源准入通过；两个全局 factor 顺序运行，前场清空后才启动后场。 |
| Q3 第一次 | `6a8b273c383d5bd9da37d6630a48bd24d6a90cce` | worker `RESOURCE_CONTROLLED_STOP`，parent `WORKER_FAILED`；在局部构建前被常驻库存预审阻止，无 F_int 调用。 |
| Q3 唯一 bug replay | `188224ad5fc81b34156a0ae3678bd2121b1206da` | **已提交、clean 的正式运行**；3 次真实 F_int 与指标已保存，随后 BAL_H map guard 抛错，worker/parent 最终 `WORKER_FAILED`。保存包重算是 `MEASURED_NEGATIVE_CANDIDATE`。 |
| Q4 original / Q5 notch | — | `not_run_after_Q3_admission_failure`；未产生本轮原 A6、完整场或 official 物理输出。 |
| Q6 证据收口 | `d9530636ab2f043a84235b515846b410a8deb4b3` | `Q6_FINALIZED`，`new_pde_actions=0`，各阶段 `read_errors={}`，固定候选关闭。 |

全部新正式 worker 的前后源码均 clean，使用同一 qualified Linux complex128/int32 ABI、MPI1、线程1。时间授权基线为 `d041da66bdcea74bdd82197cb0b8818d231b4a2d`，Review V15 base 为 `9aeee371d3ad8a3fcfcc776bd13e5e2c10518e77`。最终文档提交不改变上述阶段 source。Q6 对 Q0 只记录、未调用后继数值 checker，仍保存 `qualified=false` 和旧 EIO 的历史覆盖不完整 reason；这与 fresh Q0 worker 的核心 PASS 分列，不把旧未知终态认证为通过。

## 三份同输入的精度与准入

`rho` 是恢复后完整原 A4 残差除以原 RHS 范数；L2 和 scaled-curl 是相对既有离散参考的场与旋度差。Q1/Q2 的准确求解精度线和 Q3 的有限近似准入线不同。表中数值作显示舍入，完整精度与 RHS/参考哈希在 compact、comparison 和原始包中。

| 方法 / RHS | rho | L2 相对差 | scaled-curl 相对差 | rho / L2 / curl 限值与结果 |
|---|---:|---:|---:|---|
| Q1 原 p4 LU / A2R160_BAL_H_p4_01 | 4.24252482715e-11 | 0 | 0 | ≤1e-10 / ≤1e-8 / ≤1e-8；通过 |
| Q1 原 p4 LU / A2R160_BAL_H_p4_02 | 1.574808006e-12 | 0 | 0 | ≤1e-10 / ≤1e-8 / ≤1e-8；通过 |
| Q1 原 p4 LU / LIGHT448_BAL_H_p4_09 | 6.55690292958e-11 | 0 | 0 | ≤1e-10 / ≤1e-8 / ≤1e-8；通过 |
| Q2 准确 Schur / A2R160_BAL_H_p4_01 | 6.8106075253e-11 | 1.93827338046e-12 | 1.9386082485e-12 | ≤1e-10 / ≤1e-8 / ≤1e-8；通过 |
| Q2 准确 Schur / A2R160_BAL_H_p4_02 | 2.63094271559e-12 | 1.73249634457e-12 | 1.73407669301e-12 | ≤1e-10 / ≤1e-8 / ≤1e-8；通过 |
| Q2 准确 Schur / LIGHT448_BAL_H_p4_09 | 8.67544839197e-11 | 1.86304650554e-12 | 1.8635035518e-12 | ≤1e-10 / ≤1e-8 / ≤1e-8；通过 |
| Q3 接口近似 / A2R160_BAL_H_p4_01 | 37.2720863545 | 1.01095201255 | 1.01112382913 | ≤0.5 / ≤0.5 / ≤0.6；三项均未通过 |
| Q3 接口近似 / A2R160_BAL_H_p4_02 | 0.726414117331 | 0.962889553402 | 0.962399155213 | ≤0.2 / ≤0.9 / ≤0.9；三项均未通过 |
| Q3 接口近似 / LIGHT448_BAL_H_p4_09 | 41.8259359612 | 1.00212828377 | 1.00231965265 | ≤0.5 / ≤0.5 / ≤0.6；三项均未通过 |

Q1 的三个新求解向量与已有参考向量逐字节相同，所以表中场差为 0；这表示复现该离散参考，不是连续物理误差为零。Q1/Q2 全部无需迭代改进；它们以原 A4 精度裁决，端口增广矩阵的另一种残差仅作诊断。Q2 的作用/伴随/恢复检查约 1e-14，释放显式 Schur 后恢复差为 0，均通过原 1e-10 门槛。

Q3 的内部残差依次为 `2.98540615181059e-12 / 5.63818281749144e-14 / 2.9411258186821423e-12`，完整残差主要留在接口。主控已核对保存向量/NPZ 身份并从残差向量独立重算 rho，三项与上表一致。因此本次证据支持“准确内部消元成立，冻结接口近似纠错不足”，不推论所有 Schur 方法都不可行。

与 V13 已有四步 I4 同 RHS 的 rho `0.950231025 / 0.101264949 / 0.977895241`、L2 差 `0.964714793 / 0.877757076 / 0.992817604`、curl 差 `0.964639027 / 0.877371768 / 0.992802276` 相比，本次固定候选在三输入质量上均更差。该旧对照绑定 source `3457b5e2f54dec690fcb70deb1f387fe7f6d57cd` 和 response_v14 §7.2；未重跑旧 PC，也没有新 p6/KSP 同步数或同时间节点可比较。

## 全过程内存与完整成本

RSS/PSS 是完整 parent 进程树采样峰值，PSS 由全部可读 parent 样本取最大值；不能用 worker 稀疏 trace 代替。常驻库存是同时存活对象的保守字节账，workspace 是并存临时工作区；allocated、used 与 RSS 各有口径。以下每场费用包含该 worker 的预检、装配、构建、求解、评价、保存及清理；monotonic 与原保守时钟结算费用并列。

| workflow | RSS / PSS（B） | 常驻库存 / workspace（B） | 全流程 monotonic（s） | 保守结算费用（s） |
|---|---:|---:|---:|---:|
| Q0 fresh | 1399427072 / 1369008128 | 68803850 / 0 | 511.370434821 | 558.278084820 |
| Q1 原 p4 LU | 2825973760 / 2795549696 | 2906619390 / 17825792 | 536.468042244 | 584.770955727 |
| Q2 准确 Schur | 4267347968 / 4236889088 | 4698023554 / 17825792 | 708.431790382 | 773.019110229 |
| Q3 首次资源停止 | 2866094080 / 2835682304 | 2758151342 / 17825792 | 598.082606829 | 650.699442074 |
| Q3 唯一 replay | 3468599296 / 3438116864 | 3115588906 / 531718272 | 826.424954024 | 899.736652959 |
| Q6 只读收口 | 145199104 / 未在摘要单列 | 不作 PC 内存对照 | 2.343135095（watchdog） | 2.343456346 |

**准确 Schur 的 RSS 比为 1.5100451491807199，增加 1441374208 B；常驻库存比为 1.616318796387029，增加 1791404164 B。** 因此判为 `NO_OBSERVED_MEMORY_REDUCTION`。它是一次固定案例观测，不是统计性结论；准确 Schur 更占内存未被用来阻止后续 Q3。

| 时间口径 | Q1 | Q2 |
|---|---:|---:|
| preflight 起至首 RHS 开始的 UTC 事件区间，含完整 setup（s） | 560.968651644 | 748.901532761 |
| common setup 开始至首 RHS 的 monotonic 采样夹界，派生区间（s） | [514.603056361, 515.118303291] | [685.995946833, 686.513720302] |
| 全局 symbolic / numeric 分解自身计时（s） | 0.268321307 / 18.488779415 | 0.280450799 / 42.074472809 |
| Q2 42 个内部 symbolic / numeric 计时之和（s） | 不适用 | 0.111941312 / 0.897223226 |
| 三 RHS 调用，含 native 检查与评价（s） | 1.894626224 / 1.856757703 / 1.827990820 | 1.350819265 / 1.293319412 / 1.300694713 |

UTC 区间与 monotonic 区间有实际时钟差，不能互相减算费用或当同一个计时器。Q2 setup 包含消元装配、转换、公共正确性检查和可复用状态保存；全部计入流程。两场沿用既有 JIT cache、相同 MUMPS/V11 symbolic 配额策略，未清缓存、未启用 BLR/OOC、未升级 ABI。两场准确 factor 均存活到三 RHS 及评价完成。

| 库存组成，分别报告后端与派生口径 | Q1 | Q2 |
|---|---:|---:|
| 全局增广 rows / NNZ | 53164 / 24730144 | 13172 / 15190976 |
| 全局 factor padded allocated / padded used（B） | 2343000000 / 1382000000 | 1636000000 / 957000000 |
| 内部 42 factors padded allocated / padded used 合计（B） | 不适用 | 945000000 / 357000000 |
| 全部 factor allocated / used 合计（B） | 2343000000 / 1382000000 | 2581000000 / 1314000000 |
| 全局增广稀疏矩阵载荷（B） | 494815540 | 303872212 |
| 内部耦合 / 索引（B） | 不适用 | 789970944 / 717024 |
| 活跃体积矩阵 / 稀疏 S_V 载荷（B） | 见完整库存账 | 430410244 / 302591572 |

后端 used 略降不能替代 allocated 或完整库存通过 Gate。新增局部因子、耦合和消元填充抵消了接口行数缩减的表面优势。

Q3 首次在 `current=2758151342 B`、`projected=3331318958 B > 3221225472 B` 停止。唯一修复是在独立子块、耦合与 S_V 已建立后释放不再使用、由核心拥有的 active volume；释放 `430410244 B` 后同一预审 projected 为 `2900908714 B`，未提高 3 GiB cap。旧停止与费用保留，`unique_bug_replay_count=1`。重放构建 42 个局部 LU 与受限直接 SVD，最大 patch 768 行，候选上界 496、实际配对秩 416；局部构建 `159.270087089 s`，没有扩 rank 或步骤。单次 F_int 核心时间 `0.503379593 / 0.432578284 / 0.429629345 s`，含 native 检查与评价后为 `1.007764964 / 0.959829724 / 0.930653996 s`。每次真实计数为内部回代 168、接口局部回代 84、小粗回代 1，无旧 I4/C_U。更便宜的单次调用没有换来合格纠错。

资源规则继续为整树 min(8 GiB, 动态可用量−reserve)、reserve=max(4 GiB,15%)、Q1/Q2 常驻 6 GiB、Q3 常驻 3 GiB、临时 1 GiB。新增各场 job swap 峰值 0、global swap delta 0/0、最终子进程清空；本批 baseline 为 39/149 页，不能与旧 baseline 混算，也不据此认证工程间隙或旧 EIO 失联期间零交换。原 A6 最终 1e-6、完整物理、restart32/步数与第64步 rho≤0.10 数值门槛保留，但此次未准入 p6。

## 真实终止原因、费用历史和审阅边界

三份 Q3 指标及向量在 BAL_H 审计前已原子保存。之后实际异常为 `ValueError: Q3 p6 balanced input differs from the fresh native map`。静态检查发现 guard 用数值 map key 集合与含 `arrays`/`provenance` 的保存包 key 集合比较；这是元数据检查问题，区别于前一次 active-volume 生命周期修复。它既不证明 map 数组不同，也不证明它们已通过核验。BAL_H 保持 `NOT_COMPLETED`；小粗矩阵 E 的完整数值 rcond 未在最终失败摘要中保全，不编造该值。已保存的三输入负结果足以关闭冻结候选，没有为此再跑 PC/BAL_H、original/notch 或任何新方法。

最终共享账本在 Q6 结算后为 `4082.128437647174 s`，是 conservative-realtime 已结算费用；已结算 attempt 的 ledger monotonic 区间合计 `3738.8149168420023 s`，不包含没有该区间的 R0 采集，且不是 CPU 时间。另列旧 Q0 的 `600 s` 政策占用、`3.1 s` 保守 allowance，有效费用 `4685.228437647174 s`、名义剩余 `38514.77156235283 s`。原总额 43200 s 仍记录，本轮不据时间触发停止或准入拒绝；所有历史费用没有清零。Q6 原始 packet 嵌入的是自身结算前账本/预留，最终数以 live ledger hash `1e3b9c01745fef72f7a794b23e5077508fd65b3951485131d8b639043bd4ecb3` 为准。

旧 attempt1 的 EIO、`RESERVED` 原字段及实际耗时 unknown 保留；600 s 不是旧实测，也不是已证明的真实耗时上界。旧 attempt2 时间停止计费 `604.5503952971432 s`、旧 Q6 不完整计费 `3.9161199980033103 s`、首次 Q3 资源停止费用均在原账内。一次基础设施恢复与一次实现 bug replay 计数分别为 1；没有重跑恢复检查、旧 ABI/MUMPS/metric 资格或新建全局参考。

工程修改、监督及文档工作的完整总时长未独立计量，记 `unknown`，不伪装为 0 或并入 PDE。可核实的相关测试为时间策略主批 77 项、纯 FGMRES policy 9 项、真实 PETSc 两策略 4 项；生命周期修复 10 项和控制测试 3 项；Q6 reader 17 项，compileall/diff 检查通过。17 项测试是在 `188224ad5fc81b34156a0ae3678bd2121b1206da` HEAD 加未提交 reader 改动上运行，最终相同代码提交为 `d9530636ab2f043a84235b515846b410a8deb4b3`，不与 clean source 的正式 Q3 重放混写。主控只读数组/资源核验计时 `0.548287564 s` 单列，不重复计入 formal ledger。最终文档检查见 test_summary；未宣称 full repository pytest、Ruff 或 CI 通过，旧 Task038 registry 缺件保留。

正式输出边界仍是：没有本轮完整 p6 场、R/T/A、A_volume、全部 80 模式或守恒 Gate PASS。唯一结论是 `CLOSE_FIXED_INTERFACE_CONFIGURATION`，保留准确消元共同核心的测试证据与全部负结果，接口候选不提升 production default。5 nm 分支 HEAD `54e13335fe4313a111a33768e7b257a7a49b6541` 未受本任务修改；不合并 master，提交推送 task39extra 后等待统一审核。

证据入口：[response_v16](../response_v16.md)、[compact](records/p4_schur_v14_compact.json)、[comparison](records/p4_schur_v14_comparison.json)、[run index](records/run_index.json)、[tests](test_summary.md)。

---

# 历史快照：Review V15 初次增量（Q6 refresh 前）

本轮在同一 `task39extra` 分支上完成了授权的 R1、一次新的 Q0 和 Q6 finalization；按照共同 Q0 Gate，Q1–Q5 没有运行，也没有第三次 Q0。正式源码为 `ea5ed4cd511a9f169cd5bbf63c06f33bfed85d9e`，ABI 为 qualified Linux、PETSc `complex128/int32`、MPI1、线程 1。

| 项目 | 最终结果 | 说明 |
|---|---|---|
| R1 recovery | `APPLIED` | `V15_Q0_EIO_ONCE`；600 s policy debit；无 PDE action；恢复记录 hash `d3dffd1a97fc8492a0d0a293cecfb8a75174171ca752ed4ae1efe486dd54f418`。 |
| 新 Q0 | `PERFORMANCE_CONTROLLED_STOP` | settled `604.5503952971432 s`，reservation `600 s`，超出 `4.5503952971431545 s`；最后在 `assembly / v14_p4_volume_compile_started`，不是数值失败。树 RSS 峰值 `1769385984 B`；2151/2152 行 PSS 可读样本的峰值为 `1734977536 B`，另有 1 行 PSS 不完整，不能当作全覆盖峰值；swap `0 B`，descendants 已清空。 |
| Q1/Q2 | `not_run_after_q0_gate` | 没有配对精度和完整全过程资源，准确 Schur memory comparison 不可判定。 |
| Q3/Q4/Q5 | `not_run_after_q0_gate` | 没有接口准入或 original/notch p6 物理输出。 |
| Q6 | `Q6_EVIDENCE_INCOMPLETE` | packet 已生成；外层 exit 4/`WORKER_FAILED` 是 stage-pass 适配语义，`error=null`，没有新的 PDE action。 |

最终账本 SHA256 为 `59aa33110927596a27af04382ac7830b0631fb3a1892e3460a77d812ab6b75ba`：总预算 `43200 s`，按既定 conservative-realtime 规则结算的 workflow elapsed 字段 `613.2807354921454 s`，policy debit `600 s`，conservative allowance `3.1 s`，budget used `1216.3807354921453 s`，remaining `41983.619264507855 s`，active attempts 为空。Q6 的 settled workflow time 是 `3.9161199980033103 s`。真实 monotonic/boottime/UTC 区间另有记录；最终没有 official R/T/A、`A_volume`、衍射或守恒结果。

Q6 的回答保持保守：准确 Schur 为 `COMPARISON_INCONCLUSIVE`；接口近似逆为 `EVIDENCE_INCOMPLETE`、`Q3_admission=false`；original/notch 均未资格化；下一项为 `COMPLETE_EXISTING_REVIEW_NO_NEW_METHOD`。旧 Q0 EIO 和未知历史费用没有被抹除，新的 Q0 performance stop 也不被解释为算法失败。

主要证据入口：[Q0 run summary](../../../results/euv_grazing1_phi0/task39extra_v14_q0_core__full3d_iterative__mpi1__Mna/20260913T082401.240994Z/run_summary.json)、[Q0 watchdog summary](../../../results/euv_grazing1_phi0/task39extra_v14_q0_core__full3d_iterative__mpi1__Mna/20260913T082401.240994Z/watchdog/summary.json)、[Q6 packet](../../../results/euv_grazing1_phi0/task39extra_v14_q6_finalize__full3d_iterative__mpi1__Mna/20260913T083532.738337Z/q6_decision.json)、[最终 compact](records/p4_schur_v14_compact.json)、[最终 comparison](records/p4_schur_v14_comparison.json)。大型运行产物仍 ignored，不纳入 Git。

## 历史快照：Review V15 R0 宿主存储 Gate（后续已解除）

以下 R0 段落保留当时的宿主存储阻断和“没有 R1/Q0/PDE”状态；最终状态见上方，不以历史措辞覆盖本轮收口。

本次增量的最终状态为 **`INFRASTRUCTURE_BLOCKED`**，不是算法失败。R0 在受限 sandbox 视图中完成了两个父目录、四轮共 `16777216 B` 的原子写入/重开哈希/目录 `fsync`/自身清理探针；但宿主范围核验确认承载 Ubuntu-24.04 WSL VHD 的 Windows `C:` NTFS 卷只剩 `827174912 B`。健康状态 `Healthy/OK` 不消除这个持续性空间风险，因此没有进行 R1 账本迁移、恢复 Q0 或任何正式 PDE。

| V15 项目 | 结果 | 解释 |
|---|---|---|
| 宿主身份 | Ubuntu-24.04 → `C:\Users\admin\AppData\Local\wsl\{bb298883-9031-4854-a46f-fe067cfd0cb8}\ext4.vhdx` | 路径是 VHD 身份；`407550365696/827174912 B` 是承载它的 C: 宿主卷容量/余量，不是 VHD 文件大小 |
| 当前旧 Q0 进程 | `old_q0_matches=[]`；33 个数值进程条目 | 当前未发现旧 Q0 活跃匹配；`historical_cleanup_proven=false`，不证明历史清场 |
| ledger | SHA `b3ef68488207af8130cf906222f8699183881645ddbaa7e9cc5081b02eecf8f0`，前后不变 | snapshot 为 `old_ledger_snapshot.json`、mode `0444`；`RESERVED/active_attempt=0` 仍是未结算状态 |
| R1 / new Q0 | `not_run` / `0` | 没有正式政策扣账、没有新的 Q0、没有新的 PDE |
| 已知基础设施收集时间 | `2.387310507 s` | sandbox UTC 区间 `0.497441 s` 加宿主只读 UTC 区间 `1.889869507 s`；不是正式 PDE 费用 |
| 历史日志边界 | `incomplete` | 旧窗口命令没有明确 UTC 基准，不能证明覆盖 `2026-09-12T12:35Z` 故障窗口；journal/orphan 行不证明 EIO 根因 |

Review V15 规定的旧 `600 s` 只作为不返还的政策预算责任，本轮未写入真实 ledger；旧实际耗时仍 `unknown`。因此已知最低责任为 `602.387310507 s`，剩余只能写成 `42597.612689493 s` 上界，不能作为启动许可。Q0–Q6 均为 `not_run_by_infrastructure_gate`；V14 的 partial setup、parent `EIO`、缺失终态和 Q1/Q2 不可用记录保持原判定。

完整状态、原始报告和所有 hash 见 [response_v16](../response_v16.md) 与 [V15 I/O compact](records/v14_io_recovery_v15.json)。本页以下的 V14 内容是历史证据，不被本增量覆盖。

# Task39extra Review V14：Q0–Q2阶段证据

本页只登记现有运行目录和审计结果，不把未完成的 Q0 变成通过，也不把 Q1/Q2 缺失写成数值失败。Q0–Q2 的机器记录见 [compact](records/p4_schur_v14_compact.json) 和 [comparison](records/p4_schur_v14_comparison.json)。Q3–Q6 仍是待继续的工作，不在本页提前结项。

## 当前结论

准确 Schur 对照要求把体内未知量消元，再保留接口体积 Schur、原 80 个端口和所有内部/接口因子；它只有在 Q1 全局直接法和 Q2 准确 Schur 都完成、精度门槛相同且经历同一清理流程后，才能回答是否省内存。本次没有得到这组配对数据，因此当前答案是 `COMPARISON_INCONCLUSIVE`。

| 阶段 | 实际状态 | 运行到哪里 | RHS / 原 A4 残差 / 场 L2 / scaled-curl | 资源与时间 | 原因和边界 |
|---|---|---|---|---|---|
| Q0 `Q0_CORE` | `partial_observation` | preflight、公共预分配门、fine quadrature、P64 transfer；最后可靠 phase 为 `setup` | 均为 `not_available`；尚未准备 reviewed RHS，也没有 Q0 完成 marker | watchdog 有效前缀 373 行；树 RSS/PSS 峰值 `1,417,695,232 / 1,385,432,064 B`；job swap 峰值 `0 B`；common setup 到最后事件 `97.819706335 s`，不是完整 setup 时间 | 已知直接错误是 parent launcher 的 `EIO`；有效前缀未触发 watchdog Gate，但 worker 终态缺失，最终数值/资源分类为 `not_available` |
| Q1 `Q1_FULL_DIRECT` | `not_available` | 没有当前工作区运行目录或终态记录 | `not_available` | `not_available` | 不用 V5/V13 历史数据填充本轮 Q1 |
| Q2 `Q2_SCHUR_DIRECT` | `not_available` | 没有当前工作区运行目录或终态记录 | `not_available` | `not_available` | 不用 V5/V13 历史数据填充本轮 Q2 |

## Q0 可核对的时间线

Q0 运行目录为 `results/euv_grazing1_phi0/task39extra_v14_q0_core__full3d_iterative__mpi1__Mna/20260912T123558.964217Z`。manifest 的启动时间是 `2026-09-12T12:35:58.976504Z`。可见事件依次为：

- common preallocation gate：`12:35:59.892856Z` / `12:35:59.894340Z`；
- common setup started：`12:36:00.043279Z`；
- fine quadrature complete：`12:36:05.654845Z`；
- P64 transfer complete：`12:37:37.862986Z`。

P64 transfer 的 raw facts 包含 fine/coarse storage rows `173802/53084`、base polynomial cache `21,168,000 B` 和本地 82 个非平凡 cell permutation。它是接线/公共准备证据，不是 p4 Schur solve 或物理场结果。`workflow_phase.json` 和 watchdog 尾部都仍为 `setup`，未出现 `q0_core_complete` 或 `physical_p4_schur_v14_summary.json`。

watchdog 的 373 个有效采样覆盖到 `2026-09-12T12:37:43.112614Z`；第 374 行是 3,276 字节的 NUL/非 JSON 残留，故完整清场和终态没有证据。有效前缀的 RSS/PSS 峰值分别为 `1,417,695,232 / 1,385,432,064 B`，峰值时仍为 `setup`。5 行由 worker 触发的进程树快照（root、mpiexec、worker）的峰值为 `726,052,864 / 697,837,568 B`；这是稀疏的另一采样口径，不能代替完整树峰值。

`v14_inventory.json` 只有启动时的空清单（字段为 0）；这不表示整个 setup 期间 live inventory 为 0，故 resident inventory、workspace 峰值和 apply 时间均登记为 `not_available`。同理，watchdog 观察到 job `VmSwap=0`；全局累计计数为 `pswpin=18`、`pswpout=2039`，有效前缀内增量为 `0/0`。这里不把累计全局计数改写成 job swap，也不把前缀内增量改写成整个 workflow 的 zero-swap 证明。

## I/O 故障与 ledger 身份

可见工具记录在 `2026-09-12T12:38:19.308Z` 报告 outer `exit_code=135`。原始 traceback 的第一处故障是 `task038_launcher.py` 写 `run_manifest.json` 的 `OSError: [Errno 5] Input/output error`；异常处理随后在 `_settle_v14_shared_budget` 读取 `benchmarks/artifacts/task39extra/p4_schur_v14/review_v14/shared_workflow_ledger.json` 时再次得到同一 EIO。该记录只足以确认 parent I/O 故障；有效前缀没有触发 watchdog Gate，但缺少 worker 终态，最终数值/资源分类仍为 `not_available`，不能硬排除未知终态。

ledger 保持原样：`review_v14`、Q0 attempt 1、`status=RESERVED`、`active_attempt=0`、reserved `600 s`、`elapsed_seconds=0.0`、`unique_bug_replay_count=0`。由于 settlement 没有完成，`0.0 s` 不是实际消耗为零的结论，formal charged/settled seconds 只能写 `not_available`；本次没有手工修改预算或重放。

## 身份和证据入口

本次 Q0 绑定 source `efea244159d63a7c9db67ca091e29a9c19f9ce88`、input SHA `76e5ce396f064d7e1e7db3d0d283c7260c07cf7f0d9275783c3a10037a1afd29`、physical model SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` 和 resolved-config SHA `8c6590a404ef518bfc6f9db05ed8a6386aa152574df2d6b0ccfa1f6ac27a290d`。完整 raw 文件 hash、审计 hash 和缺失字段原因见 compact；原始大型 timeline 仍留在 ignored artifact root。

Q1/Q2 尚没有本轮 source、残差、场误差、curl、矩阵/因子 NNZ、常驻 inventory、setup/apply/cleanup 时间，也没有 memory ratio；三份冻结 RHS 名称已列入 compact，但每项数据均为 `not_available`。当前缺少共同核心的正式资格，Q3 工程实现仍需继续；后续准入按 Review V14 的共同正确性和资源条件决定，不以准确 Schur 内存节省为条件。

## 后续工程进展（不改变上述正式证据）

工程代码已提交为 `5d239140d3931364bc16d35c45458189cd957808`，固定接口候选与条件式 p6 接线的联合测试 104 passed，输入/旧 watchdog/文档另有 30 passed。没有新增正式 worker，Q0–Q2 数值字段和原 ledger 未变。实现细节、测试原始输出及已核实的推送状态见 [阶段 response_v15](../response_v15.md) 和 [工程证据](records/p4_schur_v14_engineering.json)；本次阶段记录不是 Q6 最终结项。
