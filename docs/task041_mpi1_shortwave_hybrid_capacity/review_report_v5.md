# Task041 Review V5：安全结束旧 2 nm，先排查 CPU1，再验证双路 MPI8 与双凝聚加速

## 0. 审阅决定、身份与本轮授权

**接受用户本轮方向：不再让当前低吞吐 2 nm consumer 继续消耗时间；先安全结束这一个任务并保全已完成的 QEP，再排查第二颗物理 CPU 的降频。CPU1 恢复正常后，实测 MPI8 的单路 8+0 与双路 4+4；更快且稳定才采用双路。随后选择性迁移 Task39extra 已通过的准确 p4 单元凝聚逆及必要局部内核，保留 Task041 已有的 p6 凝聚侧区与 BAL_H 数学作用，目标是把真实 2 nm 的内部迭代降至个位秒，并同时审计迭代次数与完整耗时。**

```text
repository                 = Rookie1234567/MyFEniCS
working_branch             = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date                = 2026-09-20
reviewed_base_SHA          = a9a205abc576e1db3714ecb0fd72ee2b64ea4a6e
base_latest_commit         = docs(task041): record D1e progress and packet boundary
previous_review            = review_report_v4.md
latest_response            = response_v7.md
old_D1e_running_source     = bde0686891af10bb489e4b1cb14500791cb50351
donor_branch_read_only      = task39extra
donor_audit_HEAD            = ea717ed5c6ffe45214ecdeca80cabdaeaef5960b
qualified_h10_donor_source  = b337d215c3d278d0c1e715f53e28b69f7f0ee3fe
qualified_donor_profile     = physical_p6_trace_p4_condensed_lowmem_v20
new_batch_identity         = task041_review_v5_cpu_numa_condensed_speed
response_required          = response_v8.md
formal_MPI                 = 8
mathematical_threads_rank  = 1 initially; no hidden nested threading
execution                  = R0 -> R1 -> R2 -> R3 -> R4 -> R5 -> R6
ordinary_default           = unchanged
master_merge               = NOT_APPROVED
```

本轮消除两个 blocker：一是第二路 CPU 是否可可靠使用、NUMA 布局是否浪费带宽尚未判清；二是准确 p4 侧区纠错与 A6/A4/H6 重复作用过慢，导致固定 2 nm 的大量响应不可接受。长期目标仍为 **0.7 nm、任意非可分三维周期单胞、约 2 TB 整机内存**。本轮属于硬件执行、求解器实现、内存与项目治理，不是网格收敛或 0.7 nm 资格任务；Hybrid 仍不替代通用 Full3D。

本轮用户明确覆盖旧 D2a 的“不停止、不发 signal”以及旧 D1e 的继续运行授权；覆盖范围仅限 §2 唯一确认的 Task041 D1e。新批允许 CPU/NUMA 有界对照、准确 p4 凝聚迁移、等价热点优化及 §7 条件运行。不覆盖旧结果的分类，不修改旧 task/review，不把 Task39extra 最新未合格结果改成 PASS，不干预任何邻近 Full3D。旧 V2/V4 账本保留；本批另建有明确 scope 的增量账本，不清零旧费用，也不把旧剩余额度当作无限新授权。

ChatGPT 本次只提交本 review；以下停机、硬件诊断、实现与计算均由 Codex 在工作站执行，尚不是已完成事实。

## 1. 审阅事实及两项关键纠正

来源为本分支 [Response V7](response_v7.md)、[summary](outcomes/summary.md)、[D2a compact](outcomes/records/task041_d2a_progress_20260920.json)、[V4](review_report_v4.md)，以及 §11 的固定 donor 证据。当前运行状态必须由 Codex 重新现场核对，不能沿用旧 PID 或把 9 月 20 日早间快照当实时状态。

| 对象与范围 | 已有证据 | 正确边界 |
|---|---|---|
| 工作站硬件 | 用户本轮报告：双路，每颗 24 个物理核；目前主要使用 CPU0；增加风扇后 CPU1 周围 DIMM 持续低于 80°C、接近 CPU0 | 用户提供，现场 SKU、拓扑、传感器映射及负载曲线待核验；低于 80°C 不是排除热/供电限制的充分证据 |
| Task041 5 nm BAL_H | p6/h4/M480/MPI8；worker consumer 191662.819902868 s，Schur 183016.74211002886 s | 约 53.24 h / 50.84 h；数值通过，完整公共资源/退出证据不完整 |
| Task041 2 nm D1e | W，p6/h1.5/M1200/MPI8；早间 21 个 modal 样本，470 次内部迭代，响应 elapsed 合计 49231.47518352559 s | derived 摊销约 104.75 s/内部步；不是纯 kernel，也不是正式 4800 列的完整统计 |
| D1e producer | mode-prep wall 29501.598348574014 s；selected packet 33 文件，4842723531 B，32 shard hashes 已在旧窗口核验 | 约 8.20 h；packet 已保存，但旧快照缺 public supervisor summary，复用资格尚未闭合 |
| Task39extra V20 original | 13.5 nm，Full3D p6/h10，252 hex，MPI1；112 步；原 A6 residual 9.730817853580463e-7 | 固定 original 数值/物理通过，不是 Task041 的 W/2 nm Hybrid 结果 |
| V20 内存与时间 | full-tree RSS 2831749120 B；monotonic 1479.1772295139963 s | 2.832 GB / 2.637 GiB、24.653 min；用户所说约 2.8 GB、约 26 min 应绑定此口径，而非 billing |
| donor 后续 h7.5 | 原 A6 收敛，但一次 p4 residual 2.8870661155266027e-10 > 1e-10；最新 Review V22 要求修复 | 不能将最新 donor HEAD 整体当已合格实现迁入 |

### 1.1 Task041 已经在 p6 凝聚侧区上迭代

[`physical_balanced_side_inverse.py`](../../src/solvers/physical_balanced_side_inverse.py) 明确以借用的 `HybridLocalDtnActionSystem.A` 为侧区 KSP 算子；PC 将 active residual 通过 JH 注入完整 p6，执行 BAL_H 后用 J 提取。内部 BAL_H 仍调用完整空间 A6/H6/P/PH，并持有准确 p4 因子。不能把“PC 内部有完整空间向量”误写为“侧区 Arnoldi 仍在完整 p6 空间”。

Task39extra 的 564→112 步，是其 V18 完整 p6 外层改为 V19 p6 trace＋端口外层的实测；当前 Task041 已有 p6 trace KSP，**不能再次套用该倍数**。R3 首先盘点 p6/p4 full、independent、interior、retained/port、Krylov 长度及实际因子，禁止对已消元自由度再消元。

### 1.2 准确 p4 凝聚主要改变逆的实现，不自动增强 PC

单元凝聚是在各单元内准确消去内部未知量，只对共享 trace 与保留端口建立全局因子；每次收到 RHS 时先缩减，再回代并恢复完整 p4 修正。它可能降低因子、回代、构造和内存成本，代价是局部缩减/恢复、缓存与 MPI 接线。

若完整 p4 逆、P/PH、A6/H6 和 p6 外层空间均保持等价，则 BAL_H 的数学作用应保持等价，内部迭代次数通常不应出现被预设的大幅下降。迁移的成功不强制要求步数下降；评价的是 **正确性、每步成本、每条响应成本及总成本**。若步数显著变化，必须查明是残差度量、浮点/阈值敏感性还是实际 PC/空间改变，不能仅归因“矩阵更小”。本轮不偷偷重新设计 PC 来制造迭代数收益。

## 2. R0：安全结束旧 D1e，保全证据和 QEP

### 2.1 精确确认唯一目标

旧入口仅作定位线索：

```text
unit       = task041-d1e-2nm-p6h1p5-m1200-mpi8.service
invocation = 1cf5e34338754dbfa80df487b322c72c
runroot    = /home/fenics/Projects/MyFEniCS/results/task041_2nm_balh_hybrid_iterative_p6h1p5_m1200_mpi8/task041_2nm_p6h1p5_m1200_mpi8_balh__hybrid_iterative__mpi8__M1200/20260918T095546.139183Z
```

操作前交叉检查当前 unit、InvocationID、cgroup、MainPID/starttime、全部子孙的 cmdline/cwd、input/source、runroot 和当前阶段；旧 PID 不得直接用于 signal。若已经自然完成，保留真实完成结果，不再中止；若已经结束，记录真实终态，不制造一次 stop。只有目标身份完全一致且仍活跃时才结束。

先保存轻量只读快照、当前 residual/迭代/正式列进度、RHS audits、日志 tail/offset、已有 checkpoint/manifest 与 producer 目录清单。不得为了快照复制巨量矩阵、因子或几百 GB 内存，不等待当前长 RHS 或整个 Schur 完成。不得修改正在执行的源码、原输入或 active artifacts。

### 2.2 优先协作终止，最后才处理残留

先检查既有 service、supervisor、signal handler、finalizer 和 `KillMode/TimeoutStopSec`。使用现有且确实支持的正常中止入口，让公共监督器尽可能保存真实的用户停止终态；不要臆造不存在的 checkpoint/stop API，也不要先杀 parent 再留下 MPI orphan。

若无协作入口或其无响应，按已核验的专属 unit/cgroup/进程组执行 TERM；给予明确、有界的退出宽限，默认最多 180 s，这只是停止宽限，不是 PDE 计算 timeout。随后重新核验 PID/starttime/cgroup，仅对同一任务残留执行 KILL，并记录目标、时间、信号、退出码和清理结果。保持外部观察直至该任务 cgroup 清空、RSS 回落和无 compiler/MPI 孤儿。禁止 `pkill python`、`killall mpiexec`、清空整个 user.slice 或使用邻任务的 process group。

终态记为 `controlled_stop`，reason=`USER_REQUESTED_SPEED_REDESIGN`；按原 runner 能表示的真实状态记录，并另存独立 stop audit。KILL、缺失 finalizer/public summary 或异常退出不得改写为正常 MPI 完成。没有原方程合格解时，RTA/official result 保持未取得。

邻近 Full3D、Maxwell3D-Lab、task39extra_para_workstation_capacity 或任何其他 worktree 均不在停止授权中。§3–§8 的负载与性能资格必须有独占重型运行窗口；邻 heavy 仍活跃时，只做只读硬件检查、编辑和不会造成竞争的轻量工作，记录 `BLOCKED_BY_ACTIVE_HEAVY_JOB`，不擅自停止/迁移邻任务、不后台轮询占位。

### 2.3 QEP 保留与复用边界

原 packet、32 shards、producer summaries、原始输入/physical/resolved/source/ABI/MPI/layout identities 全部保留。停机后一次流式核验文件大小和 hash，输出 `producer_reuse_audit`。p4 factor/KSP/native workspace 不在 packet 中，停机后要重建，不能声称恢复当前 RAM 中的求解状态。

优先用原 public finalizer 与 `--producer-packet-root` 验证路径。若旧入口只因整个 consumer 被用户停止而拒绝已经完整结束的 producer，允许在**停止之后的新源码**中做最小、独立测试过的受控停止资格适配：仅接受真实公共 stop/lifecycle 证据、producer 已完成/释放的原始证明、完整 packet 和全部身份检查；producer 与 consumer source 分别绑定。拒绝缺 shard、未完成 producer、错材料/mesh/MPI、错 ABI、缺公共监督证据等负例。

不得伪造旧 `supervisor_summary.json` 的成功，不得简单关闭 `require_public_supervisor_summary`，不得仅凭 hashes 完整就认定 producer 物理/布局资格。证明不足则保留文件并标 `PACKET_REUSE_BLOCKED`；不自动重跑约 8.2 h QEP，更不删除现有 packet。

## 3. R1：先排查 CPU1 是否真的异常降频

### 3.1 映射与证据优先

本报告 CPU0/CPU1 指用户说的两颗物理处理器；Linux 逻辑 CPU1、NUMA node1、BMC CPU1/CPU2 不一定是同一标签。先建立 `logical CPU -> physical core -> socket/package -> NUMA node -> BMC sensor` 映射；不得假定连续的 0–23/24–47 就是两颗 CPU，也不得把旧“CPU1–8”绑定误解成使用第二颗物理 CPU。

只读盘点至少包括 CPU 型号/stepping、每路 online 物理核/SMT、NUMA/SNC、各节点内存分布、kernel/microcode/BIOS/BMC 版本、当前 affinity/cpuset/cgroup CPU 配额、MPI 版本、实际 BLAS/MUMPS 链接与线程、governor/EPP/频率限制。可使用 `lscpu -e`、`lstopo`、`numactl --hardware`、`numastat` 和现有 BMC/内核日志；按实际工具版本选择参数。

在独占窗口，用同一受控负载、相同活跃物理核数、相同线程/ISA 与本地内存，顺序比较 CPU0 和 CPU1。先从低负载确认监测正常，再对匹配的 8 核做有界持续测试，观察至少三个稳态窗口；若短测未达到热稳态，标记暂定，不声称长期稳定。不直接开 48 核长时间烤机。

频率应采用忙时有效频率与工作吞吐；硬件支持/权限允许时记录 `turbostat` 的 Busy%、Bzy_MHz/APERF-MPERF、温度和功率，不能只用空闲均值或 `/proc/cpuinfo` 的一帧 MHz。同步记录 CPU/package、DIMM、VRM、风扇、BMC SEL/内核 thermal/MCE/EDAC/限功率信息。采样不存在时写 unknown，不臆测“未降频”。

### 3.2 要区分的原因及允许的修正

| 候选原因 | 要看的证据 | 本轮处理 |
|---|---|---|
| 空闲平均或标签误读 | busy 与平均频率、实际 core/socket mapping | 修正测量/绑定；不改硬件保护 |
| 软件限速/配额/绑定 | 每路 policy/EPP、cpuset、cpu.max、真实 rank affinity | 在权限内做最小可回滚修正，保存前后值 |
| 核心/封装温度限制 | 持续负载温度、有效频率及实时/增量 throttle 状态 | 保留保护；确认散热/风扇状态，需硬件操作时明确 blocker |
| DIMM/VRM/平台限制 | 每条 DIMM/VRM 温度、BMC 事件、平台限制证据 | 不以“DIMM低于80°C”排除其他原因；按具体型号厂商限制裁决 |
| 功率/电流/供电限制 | package power、受支持的 limit reason、两路同负载对照 | 不擅自提高 PL1/PL2/电流上限；区分配置与供电能力 |
| AVX 或正常功耗管理 | 同 ISA/核数下频率与吞吐、厂商频率规则 | 正常频率变化不是故障；不能以必须达到单核最大Turbo为Gate |
| NUMA/同步等待 | busy比例、local/remote pages、带宽、MPI等待 | 归为执行布局问题，不当成热降频修复 |

CPU1 准入要求是匹配负载下没有未解释的持续频率/吞吐缺口、无热/硬件错误、频率与厂商正常行为相符。相对 CPU0 超过约 10% 的稳定吞吐或忙时频率差作为继续调查的工程触发线，不是通用硬件健康标准；若型号不同或功耗条件不同必须先解释。记录 `CPU1_QUALIFIED_FOR_BENCHMARK`、`CPU1_NOT_REPRODUCED_WITH_LIMITED_EVIDENCE` 或明确 blocker，而不是必须虚构一个已修好的根因。

允许必要诊断工具通过仓库规定的免密 `codex-apt` 包装器安装；其他 root 操作先非交互权限探针。禁止获取/记录用户口令。BIOS/BMC 刷写、重启、改硬件电压、关闭 PROCHOT/thermal protection、超频或现场拆装不在本轮自动执行权限内；需要时保留证据并报告具体人工操作，不能用危险操作绕过故障。CPU1 未资格化时不得把它用于后续正式重负载；可在 CPU0 安全继续软件优化，并明确硬件 blocker 未关闭。

## 4. R2：保持 MPI8，验证单路 8+0 与双路 4+4

两个 socket 各四个 rank 仍是总共八个 rank、八个主要数学线程，不是 48 核全用。潜在收益来自两路内存通道/cache 与较少单路竞争，代价是跨 socket 通信和远端访问；收益必须在本程序测量，不承诺两倍。[S1–S3]

只比较下列必要配置；CPU1-only 已在 R1 用匹配负载排障，不追加完整 PDE：

| 配置 | 绑定 | 内存与不变量 |
|---|---|---|
| A | CPU0 的 8 个不同物理核 | 每 rank 1 数学线程，优先本地 first-touch |
| B | CPU0 四核＋CPU1 四核 | 总 MPI8 不变；各 rank 在目标 socket 初始化/首次写入自己的数据 |

启动前设置并回读绑定，检查 systemd/cgroup inherited `AllowedCPUs` 是否仍只允许 CPU0；不能只在命令里写双路而实际被旧 cpuset 限制。每 rank 保存 socket/core、线程数和内存节点分布；不把 SMT sibling 当不同物理核。Open MPI 的 `socket/package` 与 rankfile 参数按已安装版本验证，禁止直接复制不适用的命令。不对已经分配数百 GB 的旧进程临时改 affinity 来冒充 fresh NUMA 对照，不盲目全局 interleave 或强制所有页留在 node0。

先用小型带宽/代表性动作筛选，再在固定 5 nm 八项 RHS 上比较完整响应与主要动作。使用同源码、同输入/物理/M、同数学 PC、容差、restart、零初值、JIT/cache状态和日志级别。预先固定 A/B 顺序；至少三个稳态动作计时窗口，RHS 清单不更换。每种布局只做一次必要 setup，不为每个计时窗口重建因子。两场 fresh mesh 的原数组不能按位置直接比较；采用已证明的共同布局/持久映射或原物理 action/field 的稳定键，不重复旧 `PAIRING_IDENTITY_UNPROVEN` 错误。

选择完整响应和关键动作中稳定更快、数值/资源均通过的配置。超过 5% 且超过测量波动可判清晰收益；小幅差异允许一次有界复核，不反复测到满意。双路更慢或收益无法确认就保留 CPU0；小 kernel 快但完整响应慢不能启用。双路胜出后写成新的显式运行 profile/绑定模板，后续 R3–R6 使用它；数学内核变化后在最后 2 nm 短窗口再确认布局未反转。不把 MPI8 改为16/24/48来混淆本比较，也不同时打开 BLAS/MUMPS 多线程。[S2–S4]

## 5. R3：迁移已合格的准确 p4 凝聚，不搬整条研究分支

### 5.1 最小 donor 和接线

以固定 source `b337d215c3d278d0c1e715f53e28b69f7f0ee3fe` 的 V20 h10 合格数学路线为 donor；V19 原理、V18 p4 资格及最新 V22 的风险说明一起只读参考。建立文件/函数级 `donor_manifest`，记录来源 SHA、依赖、原 API、Task041 适配与测试。不得整体 merge/cherry-pick `task39extra`，不迁移其笔记本路径、MPI1 假设、13.5 nm Si 材料、80-mode 硬编码、旧资源规则或研究 runner。

保留当前 Task041 p6 侧区 KSP、p6/global LU=0、外层 Hybrid action/RHS、BAL_H、H6、P/PH、J/JH、原 traction、DtN、M 和正式 recovery。第一候选只将每侧完整 p4 增广因子替换为**准确 p4 单元凝聚因子＋完整逆的缩减/恢复包装**。各侧最多保留一个 p4 因子；不增加第二个完整 p6 KSP，不引入 H4/p3/普通 ILU 扫描。

### 5.2 必须实现完整逆，不只是更小矩阵的回代

令 i 为 p4 单元内部、r 为保留 trace＋原端口；对原增广算子使用一般分块：

```math
\mathcal A_4=\begin{bmatrix}A_{ii}&A_{ir}\\A_{ri}&A_{rr}\end{bmatrix},\qquad
S_4=A_{rr}-A_{ri}A_{ii}^{-1}A_{ir}.
```

每次任意 RHS g 的作用为：

```math
\widetilde g_r=g_r-A_{ri}A_{ii}^{-1}g_i,\qquad
S_4y_r=\widetilde g_r,\qquad
y_i=A_{ii}^{-1}(g_i-A_{ir}y_r).
```

恢复后才返回完整 p4 修正，并用未改写的原 physical A4 独立检查。一般内部 RHS、端口 RHS、内部端口支撑和消元后的端口块不能默认零/对角。单元 curl 与复材料质量项必须先形成完整物理局部算子再消元；不分别凝聚后相加。Floquet primal/dual、方向、共轭、slave/ghost 和外部/内部界面作用必须按原语义只应用一次。

降低阶次与消元通常不交换，不能假定 `S4 = Pt^H S6 Pt`，也不能把上述完整逆直接替换成裸 `S4^-1`。本轮优先保留现有正确的全空间传递/逆桥，而非另造 trace-Galerkin PC。

### 5.3 数值资格与内存边界

先做复数非 Hermitian 小块、非零内部/端口 RHS、单元方向/周期/MPI 空owner、重复/线性/输入不变、local recovery 和一般端口消元的独立 oracle，操作尺度相对误差默认不大于 1e-11。再做真实小 FE serial/MPI2 与 MPI8 侧区验证；不能从 donor MPI1 pass 推出 MPI8 pass。

每次返回的非零 p4 修正，原 physical A4 相对残差必须 <=1e-10；零 RHS 独立处理，近零 RHS 不用固定大分母掩盖误差。保留 Task041 已有准确逆/有界 refinement 语义；如果首次回代失败，只允许已有或明确登记的有限残差精化并计入成本，仍失败则停止。不得复制 donor 后续 h7.5 的超限结果并放宽门槛，也不得为了节省检查时间删除原 A4 检查。

同一 p6 侧区 layout/RHS 上比较旧/新完整 p4 inverse、完整 BAL_H PC 与侧区响应。复用 V4 的 P/PH <=1e-11、PC <=1e-8、每条侧区原残差 <=1e-2；响应 e_x/e_A <=1e-8 是强一致性诊断门，超出时按 V4 的数值敏感性调查，不伪造缺失映射或自动判整个 PDE 失败。输入尺度按真实范数处理。

不能同时驻留新旧两个大 p4 因子来比较。可先流式保存少量旧动作/响应与共同布局证据，再销毁旧因子、确认释放，构建新因子；p6 layout/RHS/transfer 身份需保持或被证明一致。因子仍存活时是否可释放源矩阵由当前 PETSc/MUMPS 的真实所有权决定，不能把 donor 的后端依赖警告当作可忽略事项。

局部 tensor/LU/recovery 仅在 degree、几何、材料、积分、方向、约束和端口相关身份确实一致时共享。不硬编码“永远12类”，不因当前规则结构而禁止未来非可分材料；异类单元要正确处理并记真实成本。内存账包含各 rank 复制、临时数组、local cache 与生命周期重叠，而非只报减少的 factor rows。

## 6. R4：用真实热点继续压低单步成本

准确凝聚资格建立后，仍以 BAL_H 为数学路线。按同一树/时钟的嵌套计时选择最大热点，依次做最小等价优化，而不是同时更换全部方法。

| 对象 | 允许的加速 | 必须保持/记录 |
|---|---|---|
| A6/A4 体作用 | 编译单元循环、有界批处理、张量积/sum factorization、复用固定几何/参考数据 | 同积分、材料、H(curl)方向与复数精度；不假设全局三维材料可分离 |
| p4 inverse | 凝聚缩减/回代/恢复，合理局部数据布局 | 分开计 `MatSolve`、local recovery、A4检查、refinement；准确性不减 |
| P/PH/J/JH | 已资格化批量路由/伴随内核、scratch复用、减少重复索引/分配 | 保留一致性/方向/约束检查；不回退已通过的传递优化 |
| H6 | 等价局部 kernel 与数据访问优化 | 原辅助算子、谱窗/次数和残差语义不变 |
| DtN/耦合 | 固定索引复用、bounded/streaming batch、连续数据访问 | 原所有通道与模式、phase/normalization；不显式形成巨大耦合乘积 |
| MPI/线程 | R2 合格绑定、减少不必要复制/等待 | 总 MPI8×1 为本轮主要资格；不偷偷增核或跨rank复制全场 |

Q 的 inclusive 时间包含 P/PH、p4回代、原 A4 检查与包装，不能全部算作 MUMPS；A6/H6/P/PH 的嵌套区间不能与父区间重复相加。记录完整响应 elapsed、KSP主循环、setup、独立检查/日志、每 rank 计数和临界等待，不能把不同事件的 max-rank 相加冒充端到端墙钟。

GPU、本轮 MPI16/48 扫描、新低阶 PC、近似 p4 Schur 替代 BAL_H、recycling、改变 M、降低 p/h/积分/容差均不自动授权。先完成 CPU/凝聚/热点这一条清晰对照。优化若降低内存但增加时间，保留事实，不强行启用；如果某热点确需改变数学算法而非等价实现，收口报告具体原因与数据，不现场扩展。

## 7. 执行阶梯、正式 Gate 与停止条件

| 阶段 | 授权工作 | 进入下一阶段条件 |
|---|---|---|
| R0 | 唯一旧 D1e 受控停止、证据/packet封存 | 清场与真实终态闭合；无误伤邻任务 |
| R1 | CPU1只读排障、必要安全修正、匹配负载验证 | 双路测试须CPU1准入；未准入可明确退回CPU0软件路线 |
| R2 | MPI8单路/双路有限比较，选定布局 | 数值相同、稳定性通过、端到端更快才使用双路 |
| R3 | 准确p4凝聚选择性迁移；小oracle/FE/MPI；13.5 nm完整Hybrid锚点一次 | 同方程/逆/PC/物理/资源通过；不存在未解释p4超限 |
| R4 | 5 nm固定八项同布局资格；2 nm固定少量真实响应；按热点等价优化 | 逐项原残差通过，所有修改有独立动作检查、实际时间与内存证据 |
| R5 | 最终源码下必要13.5 nm回归与一场5 nm新consumer完整回归，复用合格旧packet | 原冻结五残差、场、衍射、RTA/吸收、canonical、退出/资源全闭合 |
| R6 | 最终2 nm有界响应复核、50h容量判断；条件满足才一场2 nm新consumer全流程 | §8性能/总时间准入与全部资源/身份Gate；否则交Response V8而不再开长跑 |

5 nm八项沿用 V4 固定列：bottom `207,15,671,493`；top `310,12,666,493`。同source/layout可复用的资格不因文档更新重跑。2 nm最多选六个不同真实 RHS（每侧三个，按已保存样本覆盖快/中/慢及有意义的传播/衰减类别；不足类别如实说明），在计时前冻结 column、side、RHS/packet/hash；不是将六个 RHS 各算两次却记成六项。不得挑最好收敛的模式冒充全体。

大尺寸旧/新成对验证按共同布局与内存顺序组织，原则上每侧一次必要setup；旧运行缺布局/输出证据时允许一次最小 fresh baseline，不重跑完整旧 53 h consumer。R2的硬件比较与R3的软件比较分开固定变量；每个性能候选先通过小动作测试，再进入一批真实响应。最终2nm复核最多一批；只允许明确局部实现错误的一次受影响复测，数值/资源负结果不自动重试。

正式程序统一通过 `python scripts/run_case.py <one-case.dat>` 及既有合格 service/supervisor；MPI由当前公共入口按manifest启动，禁止嵌套两次mpiexec。组件诊断可使用已有参数化runner的显式scope，仍绑定完整dat/source/物理身份，不放进普通默认。新profile/dat独立命名，不把多个配置藏入一份dat。

最终 13.5/5 nm 与现有 exact-side/正式参考比较保持原 Task041 合同：五项 true residual <=5e-9；projection/traction <=1e-8；external-q <=1e-10；R/T/A/A_volume 差<=1e-8；selected E/H <=1e-6；canonical <=1e-5；significant-channel complex amplitude/power <=1e-6；normal flux <=1e-4；每场吸收一致性/能量闭合<=1e-5。完整通道保留，弱通道仅按原合同诊断，不加phase fit。原更严门限继续适用。

2 nm没有现成完整authority，不能伪造对照：先依赖同方程动作/响应资格；若条件完整运行，仍要独立检查原全局/两侧/modal五残差、projection/traction、复E/H、全部衍射与RTA/A_volume、原场恢复和公共生命周期。此阶段仍无新增h/M收敛资格。不得把donor的1e-6原A6门槛带到Task041的5e-9正式门槛。

## 8. 性能目标：个位秒和约50小时分开裁决

“每步”指 **BAL_H侧区内部KSP的一步**，不是最外层5步，也不是一条Schur响应或一次p4回代。至少同时报告：

```math
t_{\mathrm{step,eff}}=\frac{\sum_j T_{\mathrm{response},j}}{\sum_j n_j},\qquad
T_{\mathrm{response},j},\quad n_j,\quad \rho_j.
```

零RHS/零步样本单列；分侧报告摊销成本、各非零RHS的每步成本范围和计时分布。`response elapsed`保留与旧约104.75 s同口径的相关检查成本；可另外报告去除诊断的kernel时间，但不能用它顶替总步成本。

**明确目标为真实2 nm代表集的 `t_step,eff <=9.0 s`，并要求两侧分别达到个位秒；不靠减少容差检查、只选快RHS或更换计时定义达标。** 同时列所有RHS迭代数与完整响应时间，报告不改善/退化项。达到局部目标仅为 `REPRESENTATIVE_STEP_TARGET_MET`，不能称4800响应全体通过。

总耗时按真实路径估计：

```math
T_{\mathrm{consumer}}=T_{\mathrm{setup}}+\sum_{j=1}^{4800}T_{\mathrm{response},j}
+T_{\mathrm{outer}}+T_{\mathrm{recovery/check/output}},\qquad
T_{\mathrm{fresh}}=T_{\mathrm{producer}}+T_{\mathrm{consumer}}.
```

用户约50 h极限转成新正式consumer从启动到合格输出/收尾的 `180000 s` 目标与运行上限；不能用53.24 h旧worker口径自动放宽。fresh workflow另外报告已付producer与完整预测，不把复用QEP的warm-consumer冒充全新计算总时间。如果fresh超过50h而warm满足，必须明确写出，不能宣称二者均满足用户目标。

仅为必要条件的算术：若全部4800项每步9 s且忽略任何其他费用，50h只容许平均约4.17步/RHS；再计旧producer约29502 s时仅约3.48步/RHS，实际还需setup/outer等。因此个位秒本身不保证50h，不能承诺准确p4等价迁移必然将平均迭代降到此区间。

R6完整2nm新运行的准入必须同时满足：最终代表性单步目标、全部小/中尺度数值资格、无未解决硬件/身份/资源问题，以及基于分侧/模式类别实测、慢项与setup/outer余量的consumer规划包络<=180000 s。样本包络是带假设/不确定性的prediction，不是数学上界或可靠ETA；不能用现有样本均值不加说明外推。证据不足或预测超限即 `PERFORMANCE_TARGET_NOT_MET` / `FULL_RUN_NOT_ADMITTED`，提交具体剩余成本，不重启数月级长跑。

本批非完整PDE的负载诊断/大型组件验证累计预算24h，包含setup与失败复测，单场2nm组件上限12h；这是有界投入，不是预计耗时。读旧账、轻量代码工作与后台等待分别记录，不伪装为实测计算。R5最多一场最终5nm正式consumer、R6最多一场获准2nm正式consumer，每场上限50h；不是授权任意数量50h运行。预算不足时保存结果并收口，不反复重建因子消耗预算。

## 9. 内存、散热、环境和可靠监督

使用原生 Ubuntu/canonical worktree，先在同一shell `source .venv/bin/activate_myfenics_native.sh`；确认marker、解释器、DOLFINx/Basix、PETSc/petsc4py、MPI/SLEPc、complex128/IntType和动态库。不要为加速顺手升级ABI或重装环境。

保持内存不增加的优化方向，并按同尺寸、同scope比较；donor的2.83GB不是本任务上限。13.5/5nm组件与新5nm低内存consumer沿用旧严格tree cap `53221163008 B`，不因机器有2TB自动提高；超cap保留受控结果。2nm沿用规划1.50TiB、warning `1539316278886 B`、hard `1759218604442 B`，运行reserve至少 `412316860416 B`；launch继续核对真实MemTotal/MemAvailable、预测上界与原task更严准入。不得把D2a的642483105792 B某时刻RSS写成完整旧峰或新硬上限。

物理安全优先于性能：温度限制按具体CPU/DIMM/主板厂商规格与原BMC告警，采用更严者；保留用户关注的DIMM 80°C观察线，但不把80°C当跨设备通用安全阈值。新持续throttle、热告警、MCE/EDAC异常、供电问题、监控失鲜、swap、RSS/reserve超限或真残差失败均停止受影响运行。

job/cgroup swap=0；旧全局8192 B基线若仍存在，原样记录且新增swap/pswpin/pswpout必须为0，不对邻任务执行swapoff。整树/cgroup包含public wrapper、MPI、compiler和cleanup；RSS/PSS/USS/native factor bytes分开，缺测写unknown。保留高优先级低开销安全采样，PSS/smaps低频；性能诊断不要逐次重哈希大packet或产生重复GiB级日志，也不删除原数值检查来“提速”。

全尺寸向量/模式/因子保持分布式或流式；禁止global allgather大场、全FE×mode常驻、两套大因子重叠、OOC/BLR/低精度隐藏fallback。继续release-before-recovery，保留最小恢复packet，验证释放后原残差/物理输出及正常退出。不能把释放对象nbytes直接说成OS已归还RSS。

## 10. 交付、提交与最终回答

新增 `response_v8.md` 和一个中心 `outcomes/cpu_numa_condensed_speed_v5.md`；compact按阶段分为 `task041_v5_stop_and_packet.json`、`task041_v5_cpu_numa.json`、`task041_v5_condensed_speed.json`，包含source/input/physical/packet/layout/RHS identities、原始路径/hash、阈值、实测值与分类。原始频率/温度/性能日志、大向量与矩阵留ignored results，不新造通用监控框架。同步更新summary/test_summary、development_progress和development_model_registry，旧负结果不改写。

普通commit分开：R0轻量证据；CPU/运行绑定与必要工程修正；p4凝聚核心及focused tests；等价kernel优化及测试；clean source的有限/正式运行证据；最终Response V8。仅在当前Task041分支提交，不amend/force-push，不整体合并donor，不改master。开始前核对远端/本地tracked修改与upstream，不用reset覆盖正在进行的工作；运行SHA与本review文档SHA分开记录。若用户启用了主控/执行双窗口，内部阶段确认照仓库规则做，不要求用户逐个小测试重复授权。

Response V8顶部必须能直接回答：旧2nm如何结束、QEP是否可复用；CPU1究竟是何原因/是否仍未解；MPI8的8+0与4+4哪个更快及实际核/内存绑定；p6/p4哪些早已凝聚、哪些本轮新增；每侧p4 rows/NNZ/factor和完整RSS改变多少；真实5nm/2nm每步、每RHS、迭代数和总耗时分别怎样；个位秒和50h哪个达标、哪个未达标；完整2nm是否实际运行、何项Gate阻止；最终精度/物理/资源与残余blocker。

使用 `measured / derived / predicted / diagnostic / not_run / failed / controlled_stop / blocked` 区分事实。最终review状态仍待ChatGPT审阅，`master_merge=NOT_APPROVED`。完成或触发明确blocker即提交已有证据并停止；不得为追求PASS删除负项、放宽门槛或恢复旧无界长跑。

## 11. 固定证据与外部技术依据

仓库证据应以SHA固定，不依赖随后移动的分支HEAD：

- Task041：base `a9a205abc576e1db3714ecb0fd72ee2b64ea4a6e` 下的task、Review V4、Response V7、summary、D2a compact；`physical_balanced_side_inverse.py`与`physical_balanced_physical_operator.py`提供当前空间/逆的代码定义。
- [D1：Task39extra V20详细结果](https://github.com/Rookie1234567/MyFEniCS/blob/ea717ed5c6ffe45214ecdeca80cabdaeaef5960b/docs/task039_extra_physical_multilevel/outcomes/dual_condensed_memory_v20.md)：24.65min、2.832GB、原A4在线检查及后端生命周期；实际合格运行source为本页§0的b337d215。
- [D2：Task39extra Review V19](https://github.com/Rookie1234567/MyFEniCS/blob/ea717ed5c6ffe45214ecdeca80cabdaeaef5960b/docs/task039_extra_physical_multilevel/review_report_v19.md)：完整逆、非交换性与J M_aug JH桥，不允许只截取trace粗矩阵。
- [D3：Task39extra Review V22](https://github.com/Rookie1234567/MyFEniCS/blob/ea717ed5c6ffe45214ecdeca80cabdaeaef5960b/docs/task039_extra_physical_multilevel/review_report_v22.md)：后续h7.5的p4精度负项与尚待修复边界，不能作为已完成修复迁入。

外部资料仅说明诊断和优化机制，不证明本工作站或Task041已经加速；命令/能力以实际安装版本、SKU与权限为准（2026-09-20核对）：

- [S1：Linux CPU performance scaling](https://cdn.kernel.org/doc/html/latest/admin-guide/pm/cpufreq.html)与[intel_pstate](https://www.kernel.org/doc/html/latest/admin-guide/pm/intel_pstate.html)：频率policy、硬件反馈和请求频率的区别。
- [S2：Open MPI processor/memory affinity](https://docs.open-mpi.org/en/main/tuning-apps/affinity.html)：绑定、NUMA局部性及通信/竞争权衡。
- [S3：PETSc performance tuning](https://petsc.org/main/manual/performance/)：内存带宽、first-touch和多socket布局，不能假设更多核线性加速。
- [S4：PETSc MUMPS接口](https://petsc.org/main/manualpages/Mat/MATSOLVERMUMPS/)：实际factor后端及MPI/线程能力需核验，不是本轮自动开启多线程的许可。
- [S5：Intel Xeon thermal management](https://www.intel.com/content/www/us/en/support/articles/000006710/processors/intel-xeon-processors.html)：阈值和散热条件须按具体型号确认；非Intel SKU改查对应厂商。
- [S6：MFEM high-order performance](https://mfem.org/performance/)：partial assembly/张量积内核的实现方向，仅借鉴原理，不将MFEM基准速度当DOLFINx实测。
