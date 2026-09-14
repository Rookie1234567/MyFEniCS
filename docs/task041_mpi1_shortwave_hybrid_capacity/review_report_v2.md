# Task041 Review V2：Schur 响应链等价提速，峰值内存不增、精度不降

## 0. 结论、任务身份与授权

**接受 H2/H3 的 BAL_H 侧区替换数值成功；保留 H3 的 `RESOURCE_COMPARISON_INCONCLUSIVE`。本轮只解决一个 blocker：5 nm Hybrid consumer 的 53.24 小时中，约 50.84 小时耗在逐列构造模态 Schur 预条件矩阵所需的侧区响应。先对重复调用链做等价性能优化，不另换预条件算法，不以更多内存或放宽精度换速度。**

```text
repository                  = Rookie1234567/MyFEniCS
working_branch              = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date                 = 2026-09-14
reviewed_HEAD / base_SHA     = bab38c02d5db6c33fbdfbb800c80647acb362f87
baseline_numerical_source   = 51694bbc49d90e70eef87c953f07c695f5fc519c
original_task_base          = 50897c0c62d1f35abed5b196ae17997b2e7521cc
previous_review             = review_report_v1.md
previous_response           = response_v2.md
batch                       = task041_schur_speed_v2
execution                   = S0 -> S1 -> S2 -> S3 -> conditional S4 -> S5
response_required           = response_v3.md
formal_MPI / threads        = 8 / 1 per rank
ordinary_default            = unchanged
master_merge                = NOT_APPROVED
QEP / shorter wavelengths   = not authorized in this batch
```

用户本轮明确要求审阅全流程、寻找提速机会，并要求“内存不能上涨、求解精度不能降低”。本文授权最小性能实现、有限配对检查、13.5 nm 回归和有条件的一次优化后 5 nm 完整 consumer。覆盖 V1 的本批执行停止及性能实现范围，不覆盖其物理、数值及安全要求。不运行新的 3/2/0.7 nm，不修改正在进行的 Full3D 工作站或本机研究。活动任务材料全部留在上述分支，不创建 Task42、不整体 merge/cherry-pick donor、不写 master。

本文为代码与远端证据审阅及后续执行合同，不是 ChatGPT 新运行的性能结果。QEP 内部算法和未走入本案例的历史 solver 不作重新资格化；审阅重点是本次实际输入到 packet、consumer、Schur、嵌套 PC、恢复及公共监督的调用链。未获原始全量计时的细分瓶颈明确为待测，不用代码猜测冒充实测占比。

## 1. 先分清 QEP、Schur 构建和外层求解

证据：[Response V2](response_v2.md)、[中心报告](outcomes/side_balh_transfer_v1.md)、[compact](outcomes/records/task041_side_balh_transfer_v1.json)、[测试边界](outcomes/test_summary.md)。以下均绑定已有 H3，不混入 Task39extra Full3D 的 698 步案例。

| 范围 | 已有值 / 单位 | 数据身份及含义 |
|---|---:|---|
| 5 nm exact consumer | 1868.459373641 s | measured，同轮精确侧区对照，不含重新生产 QEP packet |
| 5 nm BAL_H worker consumer | 191662.819902868 s，53.239672 h | measured worker 时间；公共退出/资源资格另列 |
| 其中 modal Schur build | 183016.742110029 s，50.837984 h | measured 阶段；占 consumer 95.4889%，百分比为 derived |
| 其中 outer solve | 5486.829851053 s，1.524119 h | measured，5 次全局外层迭代 |
| recovery | 约 49.39 s | report 中的阶段计时，不重复加入父时间 |
| 当前 consumer QEP | 0 次 | packet 复用；`consumer_qep_required=false` |
| 历史 packet producer | 11447.683263348 s，worker-tree RSS 10039554048 B | inherited，缺完整 public-parent 覆盖；不加到本次 consumer 冒充 fresh workflow |
| candidate/exact consumer 时间比 | 102.578 倍 | derived，只比较上表两项 consumer |

**50.84 小时不是求 QEP，也不是分解一个 960 阶小矩阵所用的时间，而主要是反复计算构建该矩阵所需的上下侧区响应。** 内部 M480 表示每传播方向 480 模态，共 960 个内部系数；外部 DtN 的 600 channels 是另一套集合，不能混为 M。

用解释性分块记号表示：

```math
S_m=K_m-L_b A_b^{-1}G_b-L_t A_t^{-1}G_t.
```

代码对每个侧区计算 960 个正式模态列，共 1920 个 RHS。另有 32 个模态样本响应、8 个 cost probes、20 个外层 RHS，总共 1980 条记录。该批实际内部迭代总数 30295，p4 回代 60590；1978 个非零 RHS 正常收敛，2 个为零 RHS，单 RHS 最大 112 步，最大显式内部相对残差 0.009989594141011119。不是每次耗尽 128 步仍不收敛。

原始 RHS 索引由中心报告定位到 `consumer/numerical_output/balh_side_rhs_audits.jsonl`，文件 3852327 B，SHA256 `b84de36f3eacd82eab6ff8fad03c689bb49476efb153e7c4096fcdf61b3fc51b`。S0 直接流式读它，禁止为重取这些计数重跑 53 小时。

## 2. 实际代码链与已定位的重复工作

以下路径均相对仓库根目录，审阅基准为本页 base_SHA。新实现只能改实测热点及其必要接口，不能把这张表变成逐文件全面重构清单。

| 层级 / 主要入口 | 代码事实 | 本轮决策 |
|---|---|---|
| `scripts/run_case.py`、`src/runners/task038_launcher.py::launch_specification` | 一 dat、一公开入口，Task041 转 public supervisor；RSS/VmSwap 高频，PSS 已稀疏采样 | 保留入口/provenance；新性能选项显式绑定，不能绕开 launcher |
| `src/runners/task041_supervisor.py`、`benchmarks/task041_balh_workflow.py` | producer 可只读复用；consumer 独立 MPI8；公共终态依赖父进程存活 | 修复未来运行的持续监督与正常收尾，不追认旧缺口 |
| `benchmarks/task041_exact_side_workflow.py` | candidate setup、cost/admission、Schur、原正式 solve/recovery 编排；有 packet 身份与零 QEP 检查 | 参数化最小性能 profile；不重新求 QEP、不复制整套 runner |
| `src/solvers/hybrid_fem_modal_block_ldu.py` | 小 Schur 通过侧区逐列响应构造；full 列构建与有限 sample 对照；外层一次 PC 四次 side solve | 保持同一列集合及独立 sample，不减少 M 或替换 Schur 数学定义 |
| `physical_balanced_side_inverse.py::apply_many` | 最多 32 列的容器，内部仍逐列调用 `apply`；不是 block Krylov | 可改为 candidate 专用单列流式消费，逻辑 batch/列身份不变 |
| `physical_balanced_coupling.py` | 每次 BAL_H 两次 Q、两次 A6、一次 H6；临时向量和同一向量多次 norm | 优先复用有界 scratch 与未变化向量的 norm，保留所有检查 |
| `physical_balanced_same_mesh_transfer.py` | P 每次重算路由/排序/计数/索引交换/重复行选择；PH 逐单元构造 `matrix.conj().T` | 固定通信计划只建一次；无额外全局缓存的伴随乘法与重复行核验 |
| `physical_balanced_physical_operator.py`、`mpc_form_action.py` | Q 包含 PH、增广 RHS、MUMPS、原 A4 显式残差、P；A6/A4 体作用用 FFCx action-form 向量装配及 MPC | 不能把 Q 时间全算成 LU；分离并优化重复 packing、作用和分配 |
| `physical_balanced_h6.py`、`physical_balanced_mpc_action.py`、`physical_balanced_positive_kernel.py` | H6 固定三阶策略，谱窗 setup 时估计；runtime 已有 batch8 partial assembly | 不改变 H6 数学策略；实测需要时优化有界 kernel scratch |
| `static_local_schur_action.py`、`hybrid_local_dtn_action.py` | 侧区准确 action；静态 scatter 已复用，逐单元展开/共轭临时仍存在 | 保留原目标算子；只优化作用实现，不增加全局 p6 矩阵 |
| consumer 的既有正式恢复/比较调用 | 已产生正确复场、通道、canonical 和 flux；恢复不是当前主要时间 | 保留物理路径及 release-before-recovery，不重新设计后处理 |

表中简写的 `physical_balanced_*`、`mpc_form_action.py` 和 `static_local_schur_action.py` 均位于 `src/solvers/`。

### 2.1 不要误诊

p4 numeric factor 每侧只构建一次，nested KSP 对象也被复用，不是每个 RHS 重做 LU。原 full Schur 没有无条件完整重建两次；已有有限 sample-first 检查必须保留。H6 谱窗不是每步重估；静态侧区 scatter 不是每步重建。FFCx form 在 setup 编译/构造，不应将每次 action 向量装配误写成每次重新 JIT。

现有 candidate builder 未给 SideBalancedInverse 传入重型 checkpoint callback，默认 callback 为 no-op。183748 次 checkpoint 计数不等于 183748 次落盘/读 `/proc`，不能据此断言监控占了几十小时。独立资源采样及实际 RHS 日志的开销应另测。

### 2.2 当前计时能支持什么

compact 中保留的两个非零 RHS 示例，Q/H6/A6 的 rank-max 累计时间分别约为 `43.09/5.41/26.11 s`（13 个内部步）和 `84.19/11.23/50.15 s`（25 步）。它们支持 Q 和 A6 值得重点拆分，但不是全 1980 个 RHS 的总占比，也不能将不同分项的 MPI.MAX 相加当作一条实际临界路径。

Q 的 60590 次 p4 回代，每次还必须计算原 A4 显式残差。没有新增精化不代表没有这些作用成本。尚不能仅凭现有汇总确定 MUMPS、P/PH、A4 残差中谁最大；S0/S1 以真实计时决定先优化哪一项。

## 3. 冻结数学、物理和运行身份

本轮保留 V1/H4 真实输入的完整材料数值、几何、入射、p/h、积分、Floquet、接口法向/相位、DtN、packet 和输出。13.5 nm 为 p6/h10/M120；5 nm 为 p6/h4/M480。材料名称不在此批“顺手纠正”，不引入 Si/W 身份变化；沿各自已核验输入及 physical SHA。

```text
scalar                       = complex128
MPI / mathematical threads   = 8 / 1
fine side / global action    = original physical A_s / original Hybrid action
side solver                  = right FGMRES32, max_it128, rtol1e-2, zero each RHS
side PC                      = J BAL_H J^H, accurate physical p4 inverse
p4 true residual             = <=1e-10, at most 2 original same-factor refinements
BAL_H operation-scale audit  = <=1e-8
outer solver                 = right FGMRES32, max_it2048, zero start
full-side p6 / global factor = 0 / 0
p4 factors                   = one collective factor per side, reused
consumer QEP calls           = 0
```

精度不降首先意味着原算子、原目标解和全部终验门槛不变；不承诺浮点运算顺序改变后每个系数逐 bit 相同。旧版物理 action/独立 comparator 必须继续作为核验依据，不能同时改 fast action 和 oracle、再用二者相互证明正确。

禁止：放宽内部/外部/p4 residual；减少内部 steps 上限以省时；改 restart/初值/跨 RHS recycling；减少 M、删弱通道、增物理吸收；mixed precision、fast-math、BLR；增加 MPI/线程或未计账并行 RHS；新增 p6 精确 factor；把参考解/旧 exact 响应送入新 PC；用近似 p4-Schur、低秩模态筛选或另一套粗空间替代本轮算法。

上一轮提出的“便宜的模态 Schur 预条件器”属于后续数学研究，不在本轮静默实现。本机 p4 凝聚有潜力，但不能直接假设它会加速 Task41，更不能整体迁入 p6 双层凝聚并忽略其内存上涨。本轮先完成以下同数学提速；若不足，提交量化依据再提下一独立变量。

## 4. 性能实施：先测排序，再只做必要的两组热点优化

### A. 固定 P/PH 通信与伴随计算：优先候选

`_alltoallv_candidates` 的 owner destination、排序、send/recv counts、displacements、global IDs、source-rank 归属及重复行分组仅依赖冻结的网格/MPC/layout。允许在 setup 建立不可变计划，apply 只传数值并做同样的数值一致性核验；新紧凑计划替换旧重复表示，而不是另加一份永久索引库。全部一致性检查保留，尤其是同一 fine row 的多候选差异、MPI 空 owner、ghost、周期角点及 slave-zero。

PH 的逐单元 `matrix.conj().T` 可改为不显式复制整张共轭矩阵的伴随乘法，例如已验证的 BLAS conjugate-transpose 或有界等价 kernel。复系数和方向变换不能当成实数处理；若后端偷偷产生布局复制，计入测量。只跳过已证明没有 authority 输出的空单元，不能按数值阈值删系数。

允许复用相同 layout 的 PETSc scatter/通信计划；不新增 FE-sized allgather。不要照搬 donor MPI1 owner 快捷路径到 MPI8。A 的收益须由真实 P/PH 计时和内存账支持。

### B. 原 A6/A4 action 与 p4 解后残差：优先候选

分开记录：PH；增广 RHS/提取；MUMPS MatSolve；原 A4 显式残差；P。优先优化其中实际占比最高者。

物理 A6/A4 当前经过 `MpcFormActionContext.mult` 的 action-form 装配。允许预打包不变 constants、材料和几何 metadata，并对动态 trial-field 系数原位更新；不得错误缓存上一次 RHS 对应的 field。dolfinx_mpc 当前 ABI 是否支持相应 packed 接口须实测，不借此升级整套环境。若需要小型编译核，只做同积分、同 Piola/方向/MPC 和复材料符号的等价作用，不额外常驻一份全局 A6/A4 CSR 或逐单元大稠密张量缓存。

不能把 H6 的正定 curl-plus-abs-mass 内核直接当成带负质量项和复数损耗的物理 A6。mass、curl、端口项分别以及组合后均须与原 native action 对照。p4 每次解后的真实残差与原精化策略继续执行，不能改成“偶尔检查”或只信 KSP reason。

DtN 在当前 full-space action 中已把所有局部投影合成一次数组 Allreduce，不是每 mode 一次 Allreduce。允许替换式预处理固定 local row offsets、共轭系数、分母与 bounded scratch，不能新建 N_FE×N_modes 的大稠密 W，也不能改变弱通道、相位或投影归一化。

### C. 无额外常驻的向量/归约与 kernel 临时量

只在配对计时显示值得做时，复用原 scratch 容量、减少 create/destroy 和相同未变向量的重复 norm。缓存必须绑定向量内容版本，axpy/copy/scale 后失效；保留输入不变、非有限、BAL_H 平衡和每 RHS 真残差。合并 collective 需所有 rank 同序，保持稳健范数语义，不能以可能溢出的朴素平方和替换 PETSc norm。

不得用理论上的 p4 残差代替 `P^H` 对实际细层残差的独立检查；这会隐藏传递错误。H6 已有 batch8 与预分配工作向量，优化只替换短寿命 packing/flux/result 缓冲，不增 batch、不保留所有单元的变换后 basis。`static_local_schur_action` 的共轭/展开临时同样可有界优化，但已有固定 scatter 保留。

### D. candidate 单列流式 Schur：释放缓冲，而非假称 block 求解

原 `apply_many` 逐列独立求解；允许 candidate 按原顺序生成一列 traction、求一次 side inverse、立即 projection 写入同一 960×960 模态矩阵，再复用工作向量。保留逻辑 32 列进度、全 1920 正式响应和 32 个独立 sample；同一响应按原语义累计，不修改 exact-side 的真实多 RHS MUMPS 路径。

以 5 nm 132300 个 side rows 作示例，两个 N×32 complex128 容器的数值载荷为 135475200 B，两个单列向量为 4233600 B，差 131241600 B。这是 derived 载荷机会，不是实测 RSS 节省，更不能预先拿它支付超过该量的新常驻缓存。

该变化主要改善内存和复制；不声称它取消了内部迭代，也不保证显著提速。真正 block Krylov/recycling 在本批不授权。

### E. 日志/监督末端：有界 I/O，绝不能撤掉安全检查

`task041_supervisor.py` 的 `_sha256_file` 使用 `read_bytes()`；末端日志同步也使用 `write_bytes(log_path.read_bytes())`。对长日志这会临时读入整个文件，且末端可能发生在最后一次 worker 采样之后。允许改成固定小缓冲的流式 hash/copy、原子终态文件写入，保持完整内容与 SHA，避免新的文件体积级内存峰。历史其他未走入本批的 launcher 分支不批量重构。

原日志逐 RHS 记录继续保留。可避免重复编码/重复打开同文件，但必须有可恢复的 flush/终态约定；不把整段日志先攒在 RAM，不降低 RSS/VmSwap 采样频率来制造速度，不停止 PSS 后冒称 PSS 全覆盖。

A–C 按 S0/S1 数据选择最多两组主要热点改动，D/E 可作为最小集成的释放/收尾改动；不是授权逐项开启新的研究 campaign。若主要成本在 MatSolve 且本轮等价改动帮助有限，诚实收口，不扫描 MUMPS/BLAS 参数或另开新 PC。

## 5. 内存不增：比较对象、上限和证据必须具体

**基线是上一轮 BAL_H candidate，不是 83 GiB 的 exact-side，也不是整机 2 TB。** 比较从 fresh public launch、JIT/setup、Schur、outer、recovery、checker 到公共终态/日志复制后的全部专属进程。相同时刻各 rank/parent/compiler 的 RSS 求和；不得相加各 PID 的历史最高值。PSS/USS 另列，缺样如实报告。

13.5 nm 已有完整 consumer RSS 基准 9159106560 B；5 nm 只有旧 public 段观测峰 53221163008 B。为满足本轮不增内存，采用以下**新显式保守上限**，而不是伪造旧完整峰值：

```text
13.5 nm public consumer tree cap = 9159106560 B
5 nm public consumer tree cap   = 53221163008 B
warning                        = 90% of the applicable cap
actual cap                     = min(above cap, existing stricter safety cap,
                                     effective available minus system reserve)
```

运行中保留原系统 reserve、cgroup 有效限制、job swap=0 和全局新增换页诊断。主机预存 8192 B swap 与本任务新增活动分开，不据此隐瞒真实换页。新增监督器/采样器、JIT/链接器和最终 hash/copy 全部计入同一 cap。安全余量不足不启动，不干扰邻近 Full3D 2 nm 工作；共享工作站只允许一个 heavy case。

新优化若完整覆盖且峰值不超过旧观测值，可以写“新完整 sampled consumer peak 不高于旧已观测水平”；不能报告精确的旧完整流程降幅。共同 legacy producer 的 public 包络仍缺，不为填表重跑 QEP，也不宣称 fresh QEP+PDE 全 workflow 资源通过。

每个被改组件还须做同环境顺序配对：baseline 与 optimized 不同时常驻；比较 retained payload、同时临时上界、setup/apply RSS、全阶段峰和 native workspace。新缓存先删除/替换旧表示或缩小已有临时池，不允许因预期提速临时提高 cap。检测到总 retained 或临时量上涨时必须给出同一生命周期内更大的真实释放及总峰不增证据，否则拒绝。

采样波动不能自动给予 5% 内存放宽。存在噪声或覆盖不足可增加至多一次相关小配对复测，结果仍不明确则 `MEMORY_NONINCREASE_UNPROVEN`；不反复抽样直到出现较低峰。上述 cap 是放行策略，采样本身不构成连续时间绝对上界证明。

## 6. 精度与等价检查：保持全部旧 Gate

| 对象 | 本轮要求 |
|---|---|
| 基本线性 action / 传递 | 同输入 old/new 相对作用差不超过 1e-11；原接口已有更严限值则沿用；near-zero 按操作尺度另报绝对误差 |
| P/PH、J/JH、MPC | Hermitian dual、orientation、非零 Floquet、角点/ghost/空 rank、slave-zero、输入不变；不得删除原数值重复行核验 |
| p4 解 | 每 RHS 原 physical A4 相对残差 <=1e-10，最多原两次精化；LU 控制、矩阵和因子数量不变 |
| BAL_H 平衡 | 原 1e-8 操作尺度；同源旧 action 可独立交叉核验 |
| 内部 KSP | 原128/1e-2/FG32、zero start；reason/iterations/explicit residual 原样记录，不把 DIVERGED_ITS 重标 CONVERGED |
| Hybrid 五残差 | reported/global/bottom/top/modal 均 <=5e-9 |
| 接口 | projection 和双侧 traction <=1e-8；external-q <=1e-10 |
| 物理一致性 | 各自 abs(A_balance-A_volume)、abs(R+T+A_volume-1) <=1e-5 |
| 与 frozen exact 对照 | R/T/A/A_volume 绝对差 <=1e-8；selected E/H rel L2 <=1e-6，无相位拟合 |
| 完整输出 | 四 canonical role rel <=1e-5；全部80/600 channels保留；power>=1e-8 的并集内复幅值/功率rel <=1e-6；flux rel <=1e-4 |
| 实际实现检查 | 新旧 Vec 归属/长度、collective 次序、无复制全侧因子、无跨 RHS 数据污染；setup/apply/release 后无增长 |

微小舍入变化可能影响内部恰好触及1e-2的停止步，不硬要求全场迭代轨迹逐 bit 重合；但任何 step/reason 变化须记录并对照原 A_s，不能仅“最终低于门槛”就跳过 action 等价检查。最终比较仍使用已有 exact authority 及原输出校验，不用旧 p4 插值场替代真实 p6 输出。

测试以 pure Python/复非Hermitian小矩阵、真实小 FE、MPI2 及实际 MPI8 representative RHS 分层完成。不要求重新跑全仓每个历史 heavy case；最终变更后重跑相关 tests、scoped Ruff/compileall/文档合同。没有跑的全库 pytest/CI 不写通过。

## 7. 执行顺序与最小计算量

### S0：只读旧账，形成完整归因表

读取本目录 task/V1、response_v2、summary、全部新增补充和相关 AGENTS；核对 branch/HEAD/upstream/worktree/ABI 与实际导入路径。若 HEAD 前进，只核对差异，不 reset 或覆盖正在开发的工作树。

流式核验原1980行 SHA、分侧/分阶段计数与 wall，输出 Q/H6/A6、未覆盖区间、单 RHS median/p90/max 和总 inner work。per-rank 先累计再给 rank-max，保留真实父时钟；父子及各分项 rank-max 不相加为总 wall。若缺更细记录，标 unknown，列出下一步最小插桩，不重新创建旧 factor 只为填日志。

冻结最多8个代表性5nm RHS（每侧4个）：正/负模态、典型与最贵非零响应，依据旧日志确定 key 和 SHA；必要时可用真实 cost/outer RHS 替换，但须在测新实现前固定，不能只挑好算的。旧全场解不得用作初值或生成性能友好的 RHS。

### S1：最小插桩、非 PDE 监督修复、两组优化

先修未来监督，不修旧记录。public launcher 必须在当前工具调用/对话结束后仍被专属稳定服务或已验证的独立父进程持有；通知 observer 不能代替资源 watchdog，也不得新增孤儿接管脚本当正式运行方式。复用已有监督和组清理接口，不开发新的调度平台。

至少一次非 PDE 小进程检查覆盖：调用返回后持续采样；父失联时受控清场；MPI 自然退出且 rank `/proc` 消失；真正资源失鲜；终态记录与 wait/进程组消失一致；最终日志 hash/copy 阶段也受资源覆盖。只有样本失鲜与进程仍在运行时才按原安全状态机处理，不能在正常退出竞态中误杀再写自然退出。旧 public parent 失联的具体外因未完全证实时保留 unknown。

使用 S0 选择的8个 RHS 做一次 baseline 侧区 setup/有限求解及必要细分计时，不运行全 Schur。同样一组 RHS用于优化后的顺序配对；不在八个 rank 各建串行全侧因子。小 kernel 操作可在同对象上重复至多三次给范围，冷 setup 与重复 apply 分开。每个优化 patch 先 passing 数值和内存，再纳入总版本。

### S2：一次13.5nm优化候选完整回归

通过 S1 后，用 p6/h10/M120/MPI8、同 packet、原 exact 数组运行一次优化 candidate；不重跑已有完整 exact。保留80 channels和所有原比较；全 consumer RSS 不超过第5节值。正常退出与监控缺口必须在此关闭。先解对且内存不增再进入5nm；本场是否提速如实报告，不因小案例通信比例不同而单独否决5nm组件的明显收益。

### S3：5nm配对结论、冻结一次完整运行的入场条件

如果 S1 优化配对已覆盖最终源码且中间只改无数值文档，直接复用，不重复 setup。若 S2 暴露并修正真实实现问题，只补跑受影响的原8个 RHS，禁止换样本。

完整5nm入场要求：全部等价/精度通过；配对内存不增；固定8个RHS总 elapsed 新/旧 <=0.80；分别报告两侧及最贵源不能隐藏严重退步；根据旧各类次数和新测时间形成 Schur/consumer 预测并包含 setup/监控成本。20% 是防止为几个百分点再付几十小时的投入门槛，不是数学收敛定理。

预测必须标 predicted，列出不确定性和假设。关键计时仍 unknown、出现某侧显著退步或收益主要来自删检查/额外内存时不启动 full。最多两组主要优化后仍不满足，直接 S5 交付瓶颈及下一方案，不无界继续。

### S4：至多一次优化后5nm完整consumer

按冻结 p6/h4/M480/MPI8、原 packet、原 FG32/128/1e-2/BAL_H、原外层阈值运行。公开入口仍为 `python scripts/run_case.py <one-case.dat>`，由既有 wrapper 管理 MPI，禁止嵌套 mpiexec。性能选择及本批 cap/预算须进入 dat/resolved/manifest 或既有可审计参数合同，不能只改隐藏全局常量。

新 dat/profile 可用 `task041_schur_speed_v2` 名义扩展同一通用 runner，旧 exact 和旧 BAL_H 默认不改。实际文件路径在 S1 一次冻结，不能因 profile 名称审查又生成一套巨型 task-specific 编排。正式计算前 clean commit，run source SHA 与最终文档 SHA 分开。

保留全列构建和原独立样本、真实 inner/outer 计数、完整残差与后处理。退出前保留最小 recovery packet；销毁 KSP/PC/因子与无用对象后沿原恢复流程。监督器、public root 和所有 MPI/compiler 后代持续覆盖至最终公共文件完成及正常退出。

**不原样重跑旧53小时 BAL_H，不重新运行5nm exact，不求新 QEP，不自动做更短波长。** 数值成功但资源/速度未通过，同样提交真实结果，不为了取得漂亮比值再跑第二个数学候选。

### S5：收口

每阶段不重复请求用户确认；条件满足可在本合同内连续推进。达到安全、精度、投入上限或完成 S4 就收口，等待后续审阅。不同 worktree 可并行做代码，但本工作站 heavy lock 不得与正在进行的 Full3D 案例重叠；无权终止邻任务。

## 8. 本批投入上限、停止与判定

时间上限是计算投入政策，不是预计耗时。为避免继承已耗尽的旧 H3 账本，新增独立 V2 ledger 并链接旧 ledger，旧 203701.839373 s 覆盖、allowance、事故和用户 override 全保留。

| 范围 | 新批上限 / s | 说明 |
|---|---:|---|
| S0/S1/S3 的测试、构建和有限数值配对合计 | 21600 | 包含真实 baseline/optimized setup；不重复做长 campaign |
| S2 13.5nm完整consumer | 7200 | 同一原问题；超时为性能受控停止 |
| S4 5nm完整consumer | 172800 | 仅在 S3 有明显收益及资源证据后进入 |
| 本批计算合计 | 201600 | 上述包含关系；失败尝试也计入，不把父子wall重复收费 |

本批不自动继承旧单场 `disable-time-stop`。预算通过新的明确 opt-in 合同逐层传到 public/worker/setup/checker；旧默认与旧 override 的历史语义不变。不得将新ledger全局清零、把旧负结果改成未发生或把一次数学失败当“迁移bug”重抽签。一次明确局部工程根因修复可在剩余预算内重试受影响阶段，失败root保留；资源不足或纯数值不收敛不自动重试。

最终同时报告 numerical、time、memory、coverage 四个维度。成功目标：原完整数值/物理比较通过，优化5nm consumer及Schur时间确实下降，完整consumer采样与正常退出闭合，并满足第5节严格内存合同。若只达到组件提速，称 `COMPONENT_EQUIVALENT_SPEEDUP_MEMORY_NONINCREASE`，不升级为全场提速。内存增加为 `MEMORY_REGRESSION_REJECTED`；未证明为 `MEMORY_NONINCREASE_UNPROVEN`；精度失配、监控失败、资源/time controlled stop 分开记录。

达到新内存线、job swap或新增换页无法解释、身份/ABI失配、真实breakdown、原 action/p4/输出Gate失败或预算耗尽时按相应状态停止并清理专属进程范围。不能为了保存/通知而越安全线，也不能从文件 mtime 推断自然 MPI 退出。

## 9. 交付、提交与来源

Codex 至少提交：`response_v3.md`、`outcomes/schur_speed_v2.md`、`outcomes/records/task041_schur_speed_v2.json`；更新本任务 summary/test_summary、development progress/model registry。复用原 runner/checker/schema，新增证据只保存必要字段、固定 RHS key/hash、计时分解、对象库存、峰值覆盖、source/input/physical/resolved 与 artifact hash。不要把矩阵/因子/全量大场/多GB时间线提交Git。

报告必须回答：慢的是哪一个具体作用；每个优化删除了什么重复工作；精度检查是否全部保留；setup成本是否转移而不是消失；新缓存如何由旧对象释放支付；旧/新配对和完整consumer各省多少时间/内存；QEP是否仍0；全场未运行则列具体准入缺口。

推荐普通 commit：最小计时/监督与测试；两组经配对选择的等价热点实现及测试；必要小修复独立commit；正式结果与response。ChatGPT 本次只提交本 review，Codex负责代码与测试。无 amend/force-push/master merge；后续SHA前进先核对差异，不覆盖无关修改。

本次审查依据的核心 blob（Git blob SHA，用于识别读取源码，不替代运行 SHA）：

| 源码 | blob SHA |
|---|---|
| `physical_balanced_same_mesh_transfer.py` | `5c6f2880cbf63ea312328110fed5e21ed7a82909` |
| `physical_balanced_physical_operator.py` | `c7b088072c73dde82413c26e321f3da2e1982155` |
| `mpc_form_action.py` | `81bc14151a631ce18bff0971eecb3b8e0fde75cc` |
| `physical_balanced_coupling.py` | `d999cdfeb44218a422a06c576c535bec45df6070` |
| `physical_balanced_side_inverse.py` | `a8d7797477205d4b9450a3cd498bd505812ead2a` |
| `hybrid_fem_modal_block_ldu.py` | `9a1c2006f7fd42ba73e51f3880fce3593f67a075` |
| `physical_balanced_positive_kernel.py` | `c3afc08fac8a70d2ba42bd7a3f1dd809592802cb` |
| `static_local_schur_action.py` | `d21c71d378951708404861b58cd219631e9ff687` |
| `benchmarks/task041_exact_side_workflow.py` | `a1a167b73abb0eb6d3cc217fdbf5eed1588f0059` |
| `src/runners/task041_supervisor.py` | `eedf5444da92316051bd8b2dcbf5511ceefeb1ac` |

API原则核对：[PETSc VecScatterCreate](https://petsc.org/release/manualpages/Vec/VecScatterCreate/) 允许同layout向量复用scatter；[VecNormBegin](https://petsc.org/release/manualpages/Vec/VecNormBegin/) 的合并归约必须保持配对/调用次序；[KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/) 允许变化的内部预条件；[DOLFINx 0.10 pack_constants/pack_coefficients](https://docs.fenicsproject.org/dolfinx/v0.10.0.post3/python/generated/dolfinx.fem.html) 支持不变数据的重复装配预打包。在线 PETSc 文档不代表本机3.19所有Python接口均可用；只使用已核验的本机ABI，不为优化升级软件栈。

**最终目标仍是2TB内的0.7nm任意非可分3D。此批先证明：同一已成功的Hybrid问题可以在不多用内存、不降低精度的条件下更快完成；不能只交“外层还是5步”，也不能把未测的倍速写成承诺。**
