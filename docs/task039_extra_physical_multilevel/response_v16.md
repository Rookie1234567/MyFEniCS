# Review V15 与用户时间授权回应：准确 Schur 不省内存，固定接口候选关闭

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

证据入口：[完整阶段表](outcomes/p4_schur_v14.md)、[compact](outcomes/records/p4_schur_v14_compact.json)、[comparison](outcomes/records/p4_schur_v14_comparison.json)、[run index](outcomes/records/run_index.json)、[tests](outcomes/test_summary.md)。完整向量与原始轨迹留在 ignored artifacts；三 RHS 保存包 SHA256 为 `658a9dd4a6fcb845459a6d5f787ce8eed45d42e46813dfac440655b46bc54c35`，Q6 decision 为 `ea07b54e221a32de35cc2e47a037922833ee3135429bc90dd6ba649dcf539fe7`。主控 read-only audit（含后追加的17项测试 stdout）SHA 为 `f98926d4ed661b45156805a2a04be833124413eb487b1f01f7aef63c803d78a8`；仅移除新增 helper 子记录可复原原 audit hash `da2607bd96f6cb144ffd149c02bc2e03edf7a5953bb60720bf785d5186d4e42d`。

---

# 历史快照：Review V15 初次收口（Q6 refresh 前）

本次最终收口已按授权完成 R1、一次新的 Q0 和既有证据的 Q6 finalization；没有重试 Q0，也没有运行 Q1–Q5。源码绑定为 `ea5ed4cd511a9f169cd5bbf63c06f33bfed85d9e`，qualified WSL/Linux ABI preflight 通过：PETSc scalar `complex128`、integer `int32`、MPI1、线程 1，工作树在每个正式入口均 clean。

| 阶段 | 最终状态 | 可支持的事实与边界 |
|---|---|---|
| R0 → R1 | `APPLIED` | R0 复核证据 `ac5dc36921c33bee4da3fb490249066fb870e308d7d595975a93a5a14a4e76ba`；恢复事件 `V15_Q0_EIO_ONCE`，记录 hash `d3dffd1a97fc8492a0d0a293cecfb8a75174171ca752ed4ae1efe486dd54f418`；无 PDE action。旧 600 s 按原 reservation 不返还，且只计一次。 |
| 新 Q0 `Q0_CORE` | `PERFORMANCE_CONTROLLED_STOP` | 在 `assembly` 的 `v14_p4_volume_compile_started` 后达到 600 s reservation 的保守 realtime Gate，settled `604.5503952971432 s`，超出 `4.5503952971431545 s`；formal worker attempt `1`，completed core qualification/linear solve `0/0`；leader exit 1 是受控停止语义，descendants 已清空。没有 worker summary、RHS、A4 true residual、field L2、scaled curl 或 official result。 |
| Q1/Q2 | `not_run_after_q0_gate` | 没有匹配的全局直接法/准确 Schur 配对，因此 memory ratio、resident-inventory ratio、三份 RHS 精度和 setup/apply 比较均不可得。 |
| Q3/Q4/Q5 | `not_run_after_q0_gate` | 没有接口三 RHS 准入，也没有 original/notch 的完整 p6 求解。 |
| Q6 | `Q6_EVIDENCE_INCOMPLETE` | Q6 packet 已生成；外层 `WORKER_FAILED`、exit 4 是既有 worker-exit-4 对 `stage_pass=false` 的适配语义，`error=null`、`new_pde_actions=0`，不是新的算法异常，也不把缺失证据判成方法失败。 |

清理后 R0 的实际准入记录绑定 source `665a09b6a7d66eff15b4a744036d21f1dad3649d`；全部准入 gate 通过，C: 承载卷剩余 `37233180672 B`。4 轮 I/O probe 的实际 payload 为 `16178076 B`，与先前 `16777216 B` 合计 `32955292 B`；三项已测收集时间为 `2.387310507 s`、`2.298935873001028 s`、`0.12797381699783728 s`，另有 `3.1 s` derived correction upper bound。accepted record、raw report 和 current-kernel-check 的路径与 hash 已集中登记在 [唯一 recovery compact](outcomes/records/v14_io_recovery_v15.json) 的 `continuation.r0_recheck_after_cleanup`。

新 Q0 的正式运行目录为 `results/euv_grazing1_phi0/task39extra_v14_q0_core__full3d_iterative__mpi1__Mna/20260913T082401.240994Z`。watchdog 观察到 parent/descendant 树 2152 个样本，simultaneous RSS 峰值 `1769385984 B`；其中 2151/2152 行的同时进程树 PSS 可读，PSS 可读样本峰值为 `1734977536 B`，另有 1 行 PSS 不完整，因此不把它写成全覆盖峰值保证。job swap 峰值 `0 B`，全局 swap delta `0/0`，descendants `[]`。worker 稀疏 trace 的 RSS/PSS `1256816640/1226375168 B` 只代表另一采样范围，不能替代 watchdog 资源口径。Q0 的 monotonic/boottime 有效时长约 `551.7746 s`，但 conservative realtime/UTC 计费间隔为 `604.5503952971432 s`；两者相差约 `52.77514 s`，因此账本采用保守时钟，不把 monotonic 值当作费用。最后 phase 是 `assembly`，没有数值 solve 或物理输出。

最终共享账本位于 [shared workflow ledger](../../benchmarks/artifacts/task39extra/p4_schur_v14/review_v14/shared_workflow_ledger.json)（compact 中的绝对路径和 hash 为准），SHA256 为 `59aa33110927596a27af04382ac7830b0631fb3a1892e3460a77d812ab6b75ba`。它记录总预算 `43200 s`、按既定 conservative-realtime 规则结算的 workflow elapsed 字段 `613.2807354921454 s`、保守 allowance `3.1 s`、一次 `600 s` policy debit，最终 `budget_used=1216.3807354921453 s`、`remaining=41983.619264507855 s`，无 active attempt。这里的账本结算字段包含 R0 已测 `4.814220196998866 s`、新 Q0 settled `604.5503952971432 s` 和 Q6 `3.9161199980033103 s`；真实 monotonic/boottime/UTC 区间分别保存在 Q0/Q6 watchdog 和 parent ledger 记录中，R0 的 derived allowance 另按账本规则计入 budget used。

Q6 的最终科学边界是：准确 Schur 内存比较 `COMPARISON_INCONCLUSIVE`，因为缺少合格匹配的 Q1/Q2 accuracy 和完整 measured memory；接口近似逆 `EVIDENCE_INCOMPLETE` 且 `Q3_admission=false`；Full p6 original/notch 均未资格化；下一项为 `COMPLETE_EXISTING_REVIEW_NO_NEW_METHOD`，不支持保留准确参考作为已验证结论。没有 R/T/A、`A_volume`、衍射级或守恒量可报告。旧 Q0 的 EIO、未完成终态和未知历史费用仍保留在最终账本与 compact 中；新 Q0 的受控停止是独立的 performance negative evidence，不改写旧 EIO，也不证明算法失败。

工程编辑、监督和文档核验没有完整独立计时，按 `unknown` 登记；24 项 targeted tests 的实测 pytest wall 为 `0.17 s`，20 项 Markdown/documentation tests 为 `0.05 s`，compileall 观察 wall 为 `0.226307897 s`，均不并入正式 PDE 账本。另有 1 项历史 registry contract audit 因缺失的 Task038 文件失败，未修复无关旧证据。

Q0 raw run summary SHA256 为 `fb9d7fc023406210c44d6774e154498fced5ce5d90b050d1d16c9af65282bd2c`，watchdog summary SHA256 为 `ec4767595d63a031bd7b541c1c6b7b3ba752f26be9f55a119ff6f35925f493b8`，events SHA256 为 `043a7045efe6756a75086c14b53f4230ce1e44dc6cf7ebb4c31196f7d27b7e0d`。Q6 packet `q6_decision.json` SHA256 为 `3e1179a645d5e180851a4cf1329090021eeb190085b944d32b1d955f22a3d616`，worker summary SHA256 为 `17259b658329da691c15b43d5c56650ee413459c386711dc75871c696d87a9b7`。完整 hash 索引见 [最终 compact](outcomes/records/p4_schur_v14_compact.json)、[comparison](outcomes/records/p4_schur_v14_comparison.json) 和 [run index](outcomes/records/run_index.json)。

本轮不是完整数值任务通过：没有官方 Maxwell 输出，没有准确 Schur 节省内存结论，没有接口准入，没有 original/notch 通过。`NOT_APPROVED_FOR_MASTER_MERGE` 仍有效；可审阅的是受控停止、恢复/账本审计和紧凑证据文档，不是 production numerical qualification。

---

# 历史快照：Review V15 R0 宿主存储风险阻断（后续已解除）

以下 R0 段落保留当时的宿主存储 Gate、未执行 R1 的状态和对应 hash。最终状态已在上方记录；其中“未启动新的 Q0”等措辞只属于 R0 历史时点，不再代表当前状态。

本轮停止于 **R0：`INFRASTRUCTURE_BLOCKED`**。实际 ledger/results 目录的四轮读写核验通过，但当前 Ubuntu-24.04 的虚拟磁盘位于 C 盘，宿主查询时该卷只剩 **827,174,912 B，约 789 MiB**。这不足以排除后续文件增长的持续风险，因此按 [Review V15](review_report_v15.md) 停止正式路径，没有迁移账本或启动恢复 Q0。此报告交付的是停止证据，**原 Review V14 的数值任务尚未完成**。

| 必须回答的问题 | 本轮结论 | 缺口及原因 |
|---|---|---|
| 准确 Schur 是否省内存？ | `COMPARISON_INCONCLUSIVE` | 没有合格 Q1/Q2 配对；无法比较包含全部内部/接口因子、装配转换和恢复的全过程 RSS、常驻库存、setup 与调用时间。 |
| 唯一接口近似逆是否有效？ | `NOT_QUALIFIED` | 新接口方法没有三份真实 RHS 准入或完整 p6 证据；已有代数测试不证明效果。 |
| 完整 original/notch 是否通过？ | 本轮均 `not_run_by_infrastructure_gate` | 没有新的原 A6 残差、场/旋度或完整物理输出；不能报告通过。 |

准确 Schur 是先解并消去单元内部未知量，再解共享接口，最后恢复完整场的同方程求解方法。减少接口方程行数可能改变填充量与成本，仍须实测全部因子和全过程内存。本次存储停止没有评价它的数学优劣，也不改变“准确 Schur 不省内存仍可按共同核心和资源条件进入 Q3”的原规则。

## 实际检查、观测及证据边界

| 检查 | 实值与身份 | 可支持的结论 |
|---|---|---|
| 实际目录读写 | ledger/results 父目录各两轮，每轮 4 MiB，合计 16,777,216 B | 文件 fsync、关闭重开/hash、同目录原子重命名、目录 fsync 及重命名后 hash 均通过；自身临时文件已清理，没有第二批探针。 |
| Linux 可用空间 | 原采集显示 `851,535,978,496 B`，约 793 GiB | 是虚拟磁盘内部的文件系统余量，不能代替宿主卷的真实可用空间。 |
| 当前 WSL 存储身份 | Windows 注册的 `Ubuntu-24.04`，`ext4.vhdx` 所在卷为 C | 由宿主只读查询绑定；完整路径及原始查询保存在证据中。 |
| C 宿主卷 | 总容量 `407,550,365,696 B`；可用 `827,174,912 B` | 这些是**宿主卷**容量和余量，未测量 VHD 文件大小。空间不足以排除持续风险。 |
| 卷健康字段 | `Healthy / OK` | 是宿主报告的状态，不能抵消剩余空间风险，也不是完整介质健康证明。 |
| 当前旧 Q0 进程 | 实际 WSL 命名空间扫描 33 个 PID，无匹配旧任务 | 支持当前没有旧 Q0 活跃进程；不证明旧运行曾完整清场或其真实终止时间。 |
| 受限视图 | 初次扫描仅见 2 个 PID，`/mnt/c` 显示只读 | 是沙箱视图，不能据此宣称全机无旧进程或宿主卷只读；其原始记录完整保留。 |
| 历史异常日志 | 可见 orphan inode、恢复及 journal 非正常关闭记录 | 未建立旧 EIO 的根因。旧时段 journal 查询未明确 UTC，空结果不能证明已正确覆盖故障窗口。 |

原始 `r0_report.json` 的 SHA256 为 `d61561d645073565db1206bbdacd74faf66007c55e26fb2201e2ee793dd2da5f`；补齐实际 PID 与宿主卷口径的 `root_scope_verification.json` 为 `0485560050ed880dca11a87fda4d853f3db1ecc3f4cefbd7e045838878d696dc`。这些原始文件留在 ignored artifact 中，远程审阅入口是唯一新增的 [紧凑恢复记录](outcomes/records/v14_io_recovery_v15.json)。

## 账本、费用与没有使用的恢复额度

| 项目 | 本轮状态 |
|---|---|
| 原共享账本 | 原字节不变，SHA256 `b3ef68488207af8130cf906222f8699183881645ddbaa7e9cc5081b02eecf8f0`；旧 Q0 仍为 `RESERVED`、`active_attempt=0`。 |
| 原件快照 | 已保存相同 hash 的只读快照；没有发布后继账本或解除 active 指针。 |
| 旧真实耗时 | `unknown / null`；原 `elapsed_seconds=0.0` 是未结算字段，不是零成本。已知旧观测下界仍为 `104.12926405597166 s`，不当作完整费用。 |
| 旧 600 秒 | 不返还的政策预算责任；本轮未执行 R1，所以尚未发布政策扣款。不是 600 秒实测，也不是旧真实运行时长的已证上界。 |
| R0 原采集 | monotonic `0.497437906 s`，已保存 UTC 起止差 `0.497441 s`。 |
| 补齐口径的只读采集 | 保守时钟计费 `1.889869507 s`，没有新增写探针或 PDE；只保存核查证据。 |
| 已知采集费用合计 | 按各段较大已知时钟派生 `2.387310507 s`，低于 300 秒；应在允许恢复时计入同一原总预算。 |
| 原总预算的最低责任 | `600 + 2.387310507 = 602.387310507 s`，对应剩余额度**上界** `42597.612689493 s`；不是新的启动许可。 |
| 其他费用 | 保存/审阅的完整费用未单独计量，不能写成 0；工程编辑、Git 登记、测试与正式采集分列，未作完整工程总时长声明。 |
| 实际恢复和新运行 | 未发布恢复事件；基础设施恢复次数 0、原授权额度 1；新增 Q0 次数 0；原 `unique_bug_replay_count=0` 不变。 |

没有清零、退款、自动延期或增加阶段上限。原报告中的 `formal_ledger_debit_seconds=0` 只表示没有写账；不表示采集免费。由于账本仍阻断启动，任何代码路径均未用旧的零字段取得新的运行额度。恢复逻辑尚未资格化，本轮没有声称 parent/worker/Q6 已接入新政策账。

## 源码、测试与提交范围

Review base 为 `9aeee371d3ad8a3fcfcc776bd13e5e2c10518e77`，初次 R0 报告确认该 source 当时 clean；旧 Q0 仍绑定 `efea244159d63a7c9db67ca091e29a9c19f9ce88`。当前执行目录已原位登记为 canonical linked worktree，使用普通 `git`；原 split Git 元数据保存在 ignored 备份，源码及计算产物没有迁移。5nm 所在工作树保持原 HEAD `54e13335fe4313a111a33768e7b257a7a49b6541`。

未执行、未测试的 R1 草稿已从源码移入 ignored artifact 留档；最终 `src/`、输入及 solver 数值实现保持原字节。因此没有新算法、PC、rank、内层步骤或上限变化，仍直接沿用原 Review V14 对完整接口候选的合同。此次只提交文档和紧凑证据；[V14 合入边界](outcomes/selective_merge_manifest_v14.md) 仍为 `NOT_APPROVED_FOR_MASTER_MERGE`。

已有 `104 passed` 与另 `30 passed` 是上轮工程证据，保留其原源码与日志身份，不重报成本、不称为本轮新数值资格。本轮文档合同测试 **20 passed**，轻量 ABI preflight 确认同一 complex128/int32、MPI1、线程 1 环境，JSON/hash/diff 检查通过。详情见 [test_summary](outcomes/test_summary.md)；没有运行新的 PDE、MUMPS/metric 资格、full repository pytest 或 CI。GitHub rendered view 仍为 `not_verified`，不宣称远端渲染通过。

R1、新 Q0、Q1/Q2、条件 Q3/Q4/Q5 和正式 Q6 均因本次 R0 Gate 未运行；现有 outcomes 仅增量记录这一事实，不用占位或局部 PASS 代替完整求解。宿主存储由用户处理，后续按指令复核同一 V15 准入及预算边界，沿用原 V14 方法和未使用的恢复额度。此次不修盘、重新挂载、重启系统、迁移到 D 盘或合并 master；推送同一 `task39extra` 后统一等待审核。

---

# 历史快照：用户时间授权续算增量：显式 `time-observe-only`（当时尚未运行 PDE；不覆盖上方最终 Q1–Q6）

以下内容属于实现阶段的历史快照；后续 Q1/Q2/Q3 正式运行与 Q6 finalization 已在本文件首段另行收口。

2026-09-13，基于用户原文“先不考虑时间gate，继续推进看看”的明确授权，以及基线 `d041da66bdcea74bdd82197cb0b8818d231b4a2d`，本轮实现一个默认关闭的、只针对 `physical_p4_schur_v14` 的时间观察策略。这只是时间执行豁免，不开启新的 Review V17；原 Review V15 仍是科学合同。命令行入口为 `--v14-time-policy {enforce,observe_only}`；缺省值仍是 `enforce`，其他 profile 和 contract probe 不接受 `observe_only`。旧 attempt、旧 manifest 或旧 worker 中缺少该字段时一律按 `enforce` 解释，因此历史记录和默认路径不被改写。

`observe_only` 不把时间上限改成无穷大，也不伪造通过。共享账本仍保留固定的 `43200 s` 总额、原始阶段名和名义阶段预留；即使有效余额已经为负，观察尝试也记录完整名义预留，不把它裁剪成剩余额度。worker、parent、watchdog 和 checker 都绑定同一个 attempt policy，并保留有限、非负的原始秒数、阈值、`exceeded` 和 `time_gate_evaluated` 字段。watchdog 在子进程清场、最终保存和 cleanup 后再写一次 workflow 观察，cleanup overrun 不会消失。

观察策略只改变时间触发的停止/资格判定：PC 的 25/30 秒、Q3 单次 `F_int` 的 15 秒、接口 setup/workflow 预测、Q4/Q5 solve/workflow 时间节点以及外层 FGMRES 的 1800/5400 秒节点不再因超时主动停止；这些超时仍写入证据。FGMRES 第 64 步的数值 `rho <= 0.10` 仍是硬准入门槛，显式真残差、资源/内存、EIO、用户中止、时钟一致性、清场和有限性检查也保持有效。`solve_time_within_limit=false` 等原始事实与独立的 `solve_time_qualified` 分开保存，不能由观察模式把数值失败改写成通过。

账本中只有两个窄授权扩展：

- Q0 第三次尝试必须是 V15 recovery 后第二次 attempt 且状态严格为 `PERFORMANCE_CONTROLLED_STOP`，只允许一次 `observe_only` continuation；它不增加 `unique_bug_replay_count`，第四次仍拒绝。
- 已有 Q6 若同时具备真实 `run_summary.exit_status=4`、watchdog `WORKER_FAILED/leader_exit_code=4`、Q6 `EVIDENCE_INCOMPLETE` 且 `new_pde_actions=0`，只在**本次**显式 `observe_only` 下允许一次 `V16_Q6_EVIDENCE_REFRESH_ONCE`。它不索取或消耗 implementation-bug replay 额度；默认 `enforce` 仍走原有 bug-evidence 要求。

当前工作树已完成上述 launcher、worker、watchdog、FGMRES、checker、CLI、Q0/Q6 ledger guard 和 targeted fixture 修改；新增 compact 仅登记实现边界与轻量验证，不登记新的 PDE 数值结果。qualified activation 下的实际宿主 preflight 通过（complex128、int32、MPI1），随后两个真实 PETSc/KSP 测试各运行 `enforce` 与 `observe_only` 两种策略，共 `4 passed, 9 deselected in 0.40s`：两种策略均在单位算子测试中保持 1 步 `TRUE_RESIDUAL_PASS`，在链式算子测试中保持 64 步数值停止，KSP 数量断言不变。纯 Python policy fixture、相关 budget/recovery/watchdog/evidence/Q6/q4 mock 回归、文档/JSON/compile 检查也已通过；完整 PDE 仍未启动。当前改动尚未形成新的 clean commit，`NOT_APPROVED_FOR_MASTER_MERGE` 继续有效。
