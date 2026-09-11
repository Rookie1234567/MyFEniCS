# Task041 Review V1 / 补充任务书：BAL_H 侧区迭代替代上下层精确因子

## 0. 本轮目标、身份与权限

本轮只消除一个 blocker：**Hybrid 已经避免整个耦合系统的全局直接分解，但上下两个三维有限元侧区仍依赖完整 p6 exact factors，形成主要内存负担。将 Task39extra 已成功的物理 p4 粗修正与 BAL_H 粗细平衡机制引入这两个侧区，以完整 Hybrid 求解裁决正确性、总成本和内存收益。**

用户明确指定：先做 13.5 nm、p6/h10，再做 5 nm、p6/h4；可以继续使用 MPI8；与原 exact-side 方法比较。**5 nm 成功复现且节约内存后即收口，不自动进入下一轮验证。**

```text
repository                = Rookie1234567/MyFEniCS
working_branch            = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date               = 2026-09-11
reviewed_target_HEAD      = c08dd39bb371e3b595943ace371874777c0ff476
original_task041_base     = 50897c0c62d1f35abed5b196ae17997b2e7521cc
donor_branch              = task39extra
donor_audit_HEAD          = 4cbfadc4880c20aea775142168e6dd4e71870fda
donor_success_source      = 094204b7281fe867744fe334e8753d2faebaf89b
donor_original_solve      = 2bb6770ad00b35881558c576e7296e250656e571
method_family             = physical-p4 BAL_H side inverse + Hybrid right FGMRES
formal_MPI / threads      = 8 / 1 per rank
execution                 = H0 -> H1 -> H2(13.5nm) -> conditional H3(5nm) -> H4
response_required         = response_v2.md
ordinary_default          = unchanged
master_merge              = NOT_APPROVED
full_0p7nm_PDE            = forbidden
```

这是对 [task.md](task.md) 已有范围的用户授权扩展，不是对 [response_v1.md](response_v1.md) 的最终合并批准。此次 ChatGPT 只提交本任务书；Codex 负责实现、测试、运行和证据。

| 旧合同 | 本轮明确覆盖的范围 | 保持不变的边界 |
|---|---|---|
| 不开发 new side PC / physical p-coarse | 允许本文件规定的 BAL_H 侧区迁移和准确 p4 粗解 | 不恢复 Task040 失败候选，不扫描其他 PC |
| formal MPI1 | 本轮两个模型的 exact/candidate 均为 MPI8 | MPI1 等价性缺口不改判，不增加 MPI 扫描 |
| 原 5/3/2 nm 容量阶梯 | 本轮只执行 13.5 nm 与 5 nm 两个固定离散 | 3/2/0.7 nm、h/M 扫描、notch 与新几何均不授权 |
| 旧停止状态 | 允许启动这个独立侧区迁移批次 | 旧 3 nm physics negative、MPI1 identity/resource 缺口和失败 root 全部保留 |

全部材料和代码留在当前 Task041 分支；不创建新执行分支，不写 task39extra、其工作站分支或 master，不整体 merge/cherry-pick 大型研究分支。若执行时 HEAD 前进，先记录最新 SHA 和差异；不 reset、不覆盖本地工作，不打断既有进程。未经再次授权不得把本轮成功解释为恢复旧短波阶梯。

## 1. 证据选择：迁移成功机制，不迁移最新失败配置

本次只读核对的关键入口：根 `AGENTS.md`、`docs/AGENTS.md`、`docs/repository_work_principles.md`、`docs/markdown_rendering_standard.md`、本目录 task/response/summary；donor 的 task、V5/V12 review、response_v13、summary 与 V5 完整结果；相关 BAL_H、侧区 DtN/Woodbury 和凝聚源码。执行前还须读取这些文件的新改动及适用的更深目录规则，不重复全仓历史研究。

| 已有证据 | 确认的内容 | 不得推导的内容 |
|---|---|---|
| Task39extra V5，13.5 nm p6/h10，MPI1 | 原始/notch 为 564/576 步，true residual 约 9.9323e-7/9.3517e-7；同离散场、80 模态和物理检查通过 | 不等于 MPI8、Hybrid、5 nm 或连续网格收敛 |
| V5 粗逆 | 准确物理 p4 LU 支撑 BAL_H；p6 未整体 LU | 不是完全无因子或可扩展生产粗逆 |
| donor 最新 V12 supplement | 冻结 macro-DD 配置完整 R32 到 64 步仅为 true residual 0.766639；该配置被排除 | 不能因更新而替代 V5 成功基线 |
| Task041 5 nm p6/h4 M480 MPI8 | inherited exact-side workflow 80.025856018 GiB；本机 reproduction 80.2187461853 GiB，后者 wall 8357.347033 s | 两条是不同运行，不混用数组、时间和内存身份 |

Donor 依据固定到 [V5 完整结果](https://github.com/Rookie1234567/MyFEniCS/blob/4cbfadc4880c20aea775142168e6dd4e71870fda/docs/task039_extra_physical_multilevel/outcomes/balanced_coupling_v5.md)、[最新响应](https://github.com/Rookie1234567/MyFEniCS/blob/4cbfadc4880c20aea775142168e6dd4e71870fda/docs/task039_extra_physical_multilevel/response_v13.md) 和 [成功源码](https://github.com/Rookie1234567/MyFEniCS/blob/094204b7281fe867744fe334e8753d2faebaf89b/src/solvers/physical_balanced_coupling.py)。原始运行、恢复/notch 与文档 SHA 分开保存；历史参考的 448 页 global pswpout 归因未定也不改写。

**本轮允许每侧准确 p4 粗因子作为机制验证工具；不要求同时解决 donor 的低存储粗逆问题，也不等待另一分支的 5 nm 结果才能开始。** 可以复用后来已独立证明等价的性能修复，但须列清文件、来源 SHA 和等价性证据，不能混入新的数学 PC。

## 2. 唯一实验矩阵与冻结身份

| 阶段 | 波长 / 材料 | 有限元 / 目标 h | 内部 Hybrid 模态 | 两条对照路径 |
|---|---|---|---|---|
| H2 | 13.5 nm / Si | Nedelec p6 / 10 nm | M120 positive + M120 negative | 原 exact-side；新 BAL_H-side |
| H3，仅 H2 数值通过后 | 5 nm / W，原 Task041 数值 | Nedelec p6 / 4 nm | M480 positive + M480 negative | 原 exact-side；同族 BAL_H-side |

13.5 nm 的 M120 是本轮冻结的控制变量，不是新取得的 M 收敛结论。两条路径必须用同一个 M、同一个 packet 和外部通道集合；若 reference 自身不满足物理 Gate，保留失败并停止该阶梯，不自动增加 M。

共同几何与物理：周期 50×25 nm；z=-10…130 nm；矩形光栅宽 17×25 nm、高 120 nm；Hybrid 接口 z=10/110 nm；grazing=1°、azimuth=0°、S 偏振、入射电幅值 1；air n=1、mu_r=1；complex128、双 Floquet、Fourier-DtN、原 full3d_uniform_cg 传播与 full3d_one_cell_exact_schur traction。保持原积分、界面法向/相位、约束、动态外部模式和原始 RHS。

```text
13.5 nm: n_substrate = n_grating = 0.999002304859 + 0.00182649365 i
5 nm:    n_substrate = n_grating = 0.99396854453  + 0.00435380777 i
```

epsilon 由各自 n 的平方生成；不得把 13.5 nm Si 常数带到 5 nm，也不得换材料来促使迭代收敛。这是两个冻结材料/波长模型的验证，不宣称已隔离证明纯波长鲁棒性。

网格实际单元、独立/存储/凝聚 rows 和 external keys 由各自正式输入解析，不能抄 donor Full3D 行数当作 Hybrid 侧区行数。预期外部数量只作 sanity check，最终逐 key/order/归一化/法向/相位及数值摘要绑定。selected E/H 保留原 z=10/30/60/90/110 nm 定义；外部衍射探针必须在合法外部平面，可固定 127.5/-7.5 nm，不能把 top interface=110 nm 当作外部观测面。

新增显式 case/profile，不覆盖旧 dat 或默认配置。建议入口为：

```text
input/official/task041/side_balh/
  13p5nm_p6h10_m120_mpi8_exact.dat
  13p5nm_p6h10_m120_mpi8_balh.dat
  5nm_p6h4_m480_mpi8_exact.dat
  5nm_p6h4_m480_mpi8_balh.dat
```

这些是待实现路径，不是声称已经存在。一个 dat 仍只描述一个明确计算；producer/consumer 是该计算的既有阶段，不引入隐藏 batch 或 CLI 物理覆盖。实际 MPI8 仍经 `python scripts/run_case.py <one-case.dat>` 公开入口及其既有 MPI launcher 执行；避免 wrapper 已启动 MPI 时再嵌套 mpiexec。

## 3. 替换位置：原方程不变，侧区 inverse 改为迭代

### 3.1 区分裸 F、完整侧区算子与 Hybrid 全局算子

当前 `condensed_dtn.py` 中，消去外部 auxiliary 变量的侧区作用为：

```math
A_s=F_s-C_s H_s^{-1}D_s,\qquad s\in\{b,t\}.
```

这里 F_s 是单元静态凝聚后的裸 FE 块；C_s/D_s/H_s 是外部 DtN 组件，不能与下文粗修正混淆。原 exact-side 以 bare-F MUMPS factor 加 physical Woodbury 施加 A_s 的逆。新候选优先直接针对这个**完整物理 A_s** 做有限迭代，使用现有准确 action；不把包含 DtN 的 PC 塞进裸 F 插口再重复加入 DtN。

把两侧与内部模态重排后的解释性分块记作：

```math
\mathcal A=\begin{bmatrix}A_{\rm side}&G\\L&K_m\end{bmatrix},
\qquad A_{\rm side}=\operatorname{diag}(A_b,A_t),
\qquad S_m=K_m-LA_{\rm side}^{-1}G.
```

G/L 的代码符号继续按原存储合同，不假定互为共轭转置。**全局 MatPython action、物理 RHS、模式传播和 recovery 的目标方程必须保持原样。** 仅 PC 中的 A_b/A_t inverse 与由它们构造的 Schur 近似允许变化。

### 3.2 Full-space BAL_H 与凝聚未知量的合法桥

Donor 是 full-space p6，Hybrid 的外层侧区变量是 active trace；二者不能靠截取数组或复制 MPI1 索引连接。首选最小数学适配是：在侧区构造原 p6 全空间物理 action，令 J_s 提取保留 trace，其共轭转置把 trace 残差注入全空间并将被消去的内部 RHS 置零。正确分块下：

```math
A_s^{-1}=J_s\,\mathscr A_{s,6}^{-1}J_s^H,
\qquad M_s=J_s\,\mathcal B_{s,H}\,J_s^H.
```

第一式是精确凝聚的逆作用恒等式；第二式只是预条件器，不要求等于准确逆。新 side FGMRES 的目标仍是原 A_s，不改变原最终内部恢复。先在小型复数 FE fixture 和少量实际侧区向量上核验这条桥、边界支撑、primal/dual、Floquet 与内部 particular 项；非零物理内部 RHS 的最终恢复仍按原合同，不能错误置零。

若现有代码已有数学等价的直接 condensed-space transfer，可以使用，但须证明其 Galerkin/作用一致性；不得假定“先降 p 再凝聚”等于“先凝聚再取低阶 trace”。两种桥只选一条实现，不开启两路线性能研究。

### 3.3 迁移的 BAL_H 定义

在各自真实侧区全空间定义相容 p4 延拓 P_s，包含该侧实际材料、外部 DtN 和原界面弱形式：

```math
\mathscr A_{s,4}=P_s^H\mathscr A_{s,6}P_s,
\qquad Q_s=P_s\mathscr A_{s,4}^{-1}P_s^H,
\qquad
\mathcal B_{s,H}(r)=Q_sr+(I-Q_s\mathscr A_{s,6})\mathcal H_{s,6}((I-\mathscr A_{s,6}Q_s)r).
```

H-script 是 donor V5 的细层平滑作用，不是磁场 H。保留成功版本的组成顺序：

```text
zc = Q(r)
rc = r - A6(zc)
s  = H6(rc)
z  = zc + s - Q(A6(s))
```

迁移复共轭、owned/borrowed 向量、checkpoint 和成本计数；不恢复逐段 MR 缩步，不改成 ONE_C、BAL_S、macro-DD、普通 ILU 或新 shift 扫描。H6 需要在各侧重新构造，不能持有全 Full3D 的旧矩阵或参考场。

每侧 p4 算子/因子只构建一次、多 RHS 复用；不同侧或材料不能因 shape 相同就共用数值因子。允许准确 p4 增广因子避免显式 dense DtN。原 p4 true residual 目标 1e-10、至多两次同因子精化及 1e-8 操作尺度平衡核验保留；失败不能静默改成最新未资格化粗逆。两侧 p4 因子、矩阵和 workspace 全部计入资源账。

### 3.4 MPI8 与有限内部求解

MPI1 的 owner-route 特例不得当作 MPI8 实现。P/P^H、J/J^H、ghost、dual 加和、zero-slave、empty owner、复数全局 dot 和 communicator 生命周期须通过 serial/MPI2 小测试与实际 MPI8 侧区作用检查。每侧 p4 是一个 collective/distributed 求解对象，不在八个 rank 各建一个串行全侧因子；不得新增 FE-sized allgather 或把整个基重复存八份。原有小模态块的复制如实计账，本轮不顺带重写全部 mode ownership。

| 参数 | 首选 profile | 唯一条件性收紧 profile |
|---|---|---|
| side solver | right FGMRES，zero start，每 RHS 独立 | 相同 |
| side restart / max_it | 32 / 128 | 32 / 256 |
| side 原 A_s 相对残差目标 | 1e-2 | 1e-4 |
| side PC | 本节 BAL_H，准确物理 p4 粗解 | 完全相同 |
| 全局 Hybrid solver | right FGMRES，restart32，max_it2048，zero start | 完全相同 |
| 全局终验 | 第 6 节全部 Gate，绝不采用 donor 的 1e-6 代替 | 完全相同 |

内部目标是提前返回和质量标签，不是每个 RHS 必须达到的外层入场线。达到合法步数预算而未达目标时可返回有限近似，保留真实 residual、KSP reason 和 `INNER_APPROXIMATE_RETURN`；非有限、错误接线、真正 breakdown、资源违规不在此例外中。不得把 inner DIVERGED_ITS 改写成 CONVERGED，也不得让它自动杀死本可由外层纠正的解。

首选完整 Hybrid 已通过则不运行收紧版。只有正确性/安全通过，而有限完整外层或 setup 记录表明 side inverse 质量不足时，才允许该唯一收紧对照；每个波长至多两次 candidate 完整运行，不改其他参数。先在 13.5 nm 冻结实际成功参数，再原样带入 5 nm；5 nm 不复跑已排除的较弱设置，不增加第三种设置。不得要求一个固定 RHS 做几百次诊断才允许完整外层，也不要求一次 PC 作用的残差必须下降。

### 3.5 近似 Schur、solve_many 与 exact-only API

现有 Woodbury oracle 的 `factor_only_storage`、`solve_many` 及 exact residual 契约不能被伪造标志绕过。候选使用明确命名的新 side inverse adapter；保留原 exact 类和默认调用。全局 block-LDU 的所有 side 调用、构建期模态响应列及 recovery 依赖均须盘点，确保没有隐含 p6 factor。

允许在 PC setup 中用新 side inverse 逐列/至多32列 streaming 构造固定的 Schur **预条件矩阵**。由于有限 Krylov inverse 一般非线性，逐列得到的矩阵不能被宣称为任意 RHS 下精确的线性逆作用，也不能冒充原 S_m。其后小型模态块 LU 允许；不得增加未计账的全侧响应库，不能复用旧 exact factors 算出的 side response 来帮助 candidate。

FGMRES 允许变化/非线性 PC，不允许借此随意改变原全局 operator。与 inexact side 有关的所有误差留在 PC 一侧；原 Hybrid explicit residual 始终独立重算。禁止将近似 Schur 当作真实 reduced operator 而只报告其自身 residual。

构建前用少量真实正/负模态 traction、external 与一般残差 RHS 测成本，列出实际列数、每侧 solve 数及预计 setup 上界；高成本不能藏在 outer iteration=1 后面。预算明显不容纳时以 `SETUP_COST_BLOCKED` 收口，不回退到精确 p6 factors，也不在本轮重构 QEP/传播算法。

## 4. H0/H1：窄迁移与一次合并准入

H0 核对当前分支/HEAD/upstream/canonical worktree、dirty status、原生 activation、每 rank ABI、complex128/IntType、MPI/线程、内存、swap、disk、watchdog 及两项目资源排他。按根规则使用 `source .venv/bin/activate_myfenics_native.sh`；不为文档或小测试安装新求解栈。

记录 source/target 文件级迁移表。优先参考 donor 的 `physical_balanced_coupling.py`、`physical_balanced_runtime.py` 及其 p4/H6 最小依赖；接入 target 的 `hybrid_local_dtn_action.py`、`hybrid_local_dtn_woodbury.py`、`condensed_dtn.py` 和现有 Hybrid PC 接口。数值实现进入 `src/`；runner 只负责输入、资源和证据。不得复制完整 donor runner 或整个研究目录。

H1 将代数、真实 FE、MPI 与输入测试合并为必要的 focused suite：复共轭；P/J 双向传递；Galerkin/凝聚作用相对差不超过1e-10；原全局 action/RHS 对照相对差不超过1e-12；zero/finite/input不变；重复新 RHS 不串状态；合法内层预算返回；factor 计数；destroy 与异常退出；新旧 profile 隔离。零分母按明确绝对尺度检查，不除以理论为零的量。

小测试可用精确矩阵作 oracle，但不能替代 H2/H3。实际侧区采用少量可复用向量，不做新的大规模 PC 筛选。必要准入通过后直接进入 H2，不在每个小步骤后请求用户重新授权。若用户已启用主控/执行双窗口，保留其内部审核职责，但不据此扩大任务。

## 5. H2/H3：同方程 exact/candidate 对照

每个波长先绑定 reference，再运行 candidate。优先复用同机、同 MPI8/线程、同离散/模式/边界和完整数值数组/telemetry 可读的已合格 exact-side evidence；源码或 schema 不同需有明确数值等价桥，不能凭相近 R/T/A 拼接。缺少匹配 reference、全场或可靠资源口径时，允许该波长至多一次 fresh exact-side 基线；不重跑 Full3D direct 或 global Hybrid direct。

Exact 基线可以使用原 p6 side factors，但必须单独进程运行、完整测量并彻底释放，然后才启动 candidate。参考答案只在评价端读取，不能进入 candidate 初值、PC、模态响应或方向选择。

同波长共用冻结的 selected-mode packet。已有 packet 符合物理/离散/ABI/MPI8/owner 身份时复用，不重做 QEP；缺失时允许一次既有 producer，完全退出后再启 consumer。不得把 MPI1 owner-sharded packet 直接当 MPI8 packet。

H2 完成 13.5 nm 原系统求解、recovery 和全部同离散比较后进入 H3；小案例不强求节省固定比例，资源结果照实列出。若只有字段/观测输出错误，允许从同一合格 solution checkpoint 恢复，不重解清洗失败。数学或物理 Gate 未过则按允许的唯一条件对照分流，仍未过则停止，不进入 5 nm。

H3 固定 5 nm p6/h4 M480，运行从 H2 带来的配置；与合格 exact-side 比较全部输出和全生命周期资源。**5 nm 完整数值复现且有可信内存节省后，立即进入 H4；即使效果很好也不启动 3 nm、2 nm、0.7 nm、网格/模式扫描或非可分新模型。**

## 6. 数值与物理 Gate：按 Task041，而非放宽到 donor

| 类别 | 两个波长均适用的要求 |
|---|---|
| 线性系统 | reported、global explicit、bottom、top、modal residual 各不超过5e-9；保留原归一化定义及正的 outer KSP reason |
| 接口与源 | projection、每侧 exact traction 不超过1e-8；external-q identity不超过1e-10；原相位/法向/约束完整 |
| 独立守恒 | abs(A_balance-A_volume)不超过1e-5；abs(R+T+A_volume-1)不超过1e-5；A_balance定义闭合另报 |
| exact/candidate 总量 | R/T/A_balance/A_volume绝对差各不超过1e-8 |
| exact/candidate 场 | selected复E、复H整体相对L2各不超过1e-6；canonical active/full向量相对差不超过1e-5 |
| 衍射 | 两结果功率至少1e-8的显著通道并集，功率/复幅值相对差各不超过1e-6；全部通道完整输出 |
| 身份与近零量 | 同坐标、同材料/网格/M/external physical keys；不拟合全局相位；近零量采用原checker约定并补绝对差，不扩大分母掩盖错误 |
| 完整恢复 | 原 E/H、near field、normal flux、canonical vectors、全部衍射级及体吸收；不得仅有标量summary |

优先复用 Task041/Task039 已有 comparator，不得为 candidate 放宽旧阈值。原参数表若未显式规定某个近零量的绝对门槛，必须在 H0 比较合同中预先冻结并说明尺度，不能看过误差后设限。

未过原方程 residual 的场只能作 diagnostic，不能发布 official R/T/A。缺少参考数组为 `REFERENCE_EVIDENCE_INCOMPLETE`，不是 matched pass；必要 fresh 基线也无法提供时收口。两例成功只说明这两个固定 Hybrid 离散的代数复现，不是 p/h/M 收敛或任意三维/波长鲁棒证明。

## 7. 内存、时间与生命周期

### 7.1 候选的因子合同

```text
full_p6_bottom_factor_count       = 0
full_p6_top_factor_count          = 0
global_Hybrid_direct_factor      = 0
global_Full3D_direct_factor      = 0
hidden_exact_side_response_cache = forbidden
accurate_p4_side_coarse_factors  = allowed, counted, at most one logical factor per side
cell_interior / small_modal_LU   = allowed, counted
silent_direct_fallback          = forbidden
```

因此成功可称“p6 全侧因子替代及固定案例低内存成功”，不可称 factorization-free。若 p4 LU 成为新主峰或增长瓶颈，如实报告；其进一步低存储化不在本轮。

### 7.2 本批硬安全和投入上限

| 项目 | 13.5 nm | 5 nm |
|---|---:|---:|
| process-tree RSS warning / hard | 48 / 64 GiB | 224 / 256 GiB |
| 每次 exact 或 candidate 完整 consumer wall cap | 14400 s | 43200 s |
| 需要时一次 packet producer wall cap | 18000 s | 18000 s |
| 整批累计计算上限，含失败/对照/必要测试/producer | 172800 s，共享，不逐阶段重置 | 同左 |

这些是本轮有限投入上限，不是预计完成时间。有效 hard cap 还须取阶段上限、可见物理/cgroup可用量扣除安全余量后的较小值。保留至少384 GiB整机 MemAvailable，并监测有效cgroup余量；实际资源不支持时不启动。不得套用 donor 笔记本2/2.5 GiB组件 cap，也不得借约2 TB物理内存把上述线自动提高。

swap使用与本次运行活动均为0；记录job和global口径。一次只跑一个heavy，和并行项目通过排他锁/运行登记协调；别的heavy仍运行就排队或记录RESOURCE_BUSY，不擅自终止它。监督范围包含MPI、parent、JIT/compiler及所有后代；硬线优先于保存完整审计。

计数每个 side RHS、内部步数/BAL_H/p4回代、外层matvec/PC、Schur列和batch；分别报告setup、QEP、构建、求解、true residual、recovery、cleanup。父子嵌套时间不重复相加。不得以outer少于几步或某次side solve很快代表整个workflow快；没有达到内部软目标也不自动判完整solver失败。

不套用donor笔记本的1800s screen或固定第32步残差线；本轮由明确完整预算、非有限/真实breakdown/正确性和硬资源边界停止，不无限续跑。工程错误允许保留旧root后最小修复和针对性重跑，同根因至多一次formal retry；数学失败不是bug。

### 7.3 公平资源比较与最终成功线

记录同期process-tree RSS、可读PSS/USS、每rankRSS、采样频率/缺样、cgroup peak、swap、scratch和MUMPS inventory。将p6 operator carrier、p4矩阵/因子、H6/transfer、DtN C/D/H、原或新W/K、Schur、内外Krylov及recovery逐项列出，同时存活与阶段释放分开。

```math
\eta_{\rm consumer}=1-B_{\rm candidate}/B_{\rm exact}.
```

上式只比较相同测量口径、相同阶段覆盖和缓存政策下的完整consumer峰值，不比较单rank峰和全树峰。报告节省GiB/百分比及总时间比；没有硬设50%节省目标，也不要求candidate必须更快，但必须在预算内完成。微小差异不足以排除已知采样/重复性波动时为 `RESOURCE_COMPARISON_INCONCLUSIVE`，不能强写内存成功。

producer与consumer不重叠时，完整计算的峰值取两阶段max。复用历史producer时，可以列出共同producer与两个新consumer组成的比较包络，但必须标为 `derived_common_producer_envelope`，不冒充新的不中断workflow实测；历史基线80 GiB若覆盖producer也不能直接和candidate consumer-only峰混算。若共同producer主导而总包络没有降低，明确“consumer节省、总峰未下降”，不升级为完整workflow节省。

本轮目标成功要求：H2/H3数值与物理复现均通过；5 nm上下侧p6 factor均为0；5 nm完整consumer有可信正节省；共同producer口径下完整峰值也降低；资源、provenance及完整输出闭合。若完整峰值只有derived证据，状态和结论明确保留这一限定，不能标measured end-to-end。缺可信共同producer资源则只给consumer结论，不批准后续规模验证。

成功或停止均执行安全清场。合格解按 `true residual -> minimal recovery packet -> destroy KSP/PC/p4 factors/unneeded matrices -> record RSS -> recovery -> final cleanup`；若allocator导致RSS未降，如实保存对象销毁与实测，不伪造释放。旧exact与新candidate采用同样生命周期和采样政策。

## 8. 交付、状态与停止边界

H4在同一目录提交一个中心报告 `outcomes/side_balh_transfer_v1.md`、一个对应compact JSON及必要run/输入/原始artifact索引，更新现有summary、development_progress和development_model_registry，新增 `response_v2.md`。不创建大量平行解释文件，不删除原Task041结论。

每个正式root保存 `input_original.dat`、`resolved_config.json`、`run_manifest.json`、input/physical/source SHA、`run_summary.json`、环境/MPI/资源/factor inventory、packet/external identities及artifact hashes。大场/矩阵/因子/日志仍在ignored目录；同一个比较pair绑定各自准确源码，文档提交SHA不能替代运行SHA。

| 本轮终态 | 含义与后续 |
|---|---|
| PASS_FIXED_CASES_WITH_MEMORY_SAVING | 两模型复现、5 nm可信节省；停止并等待review，不启动更短波长 |
| PASS_NUMERICAL_ONLY_NO_MEMORY_GAIN | 解对但未省内存；停止，不扩大模型 |
| PASS_CONSUMER_MEMORY_WORKFLOW_UNQUALIFIED | consumer通过，完整包络未证明降低或缺证据；停止 |
| RESOURCE_COMPARISON_INCONCLUSIVE | 差异或测量不足以支撑节省；停止并列明缺口 |
| NUMERICAL_OR_PHYSICS_FAIL | 具体量、实际值/限值、失败阶段和原始解证据完整保留 |
| RESOURCE_BLOCKED / SETUP_COST_BLOCKED / TIME_CONTROLLED_STOP | 与数值失败分开，不自动升cap或换算法 |
| IMPLEMENTATION_FAILURE / REFERENCE_EVIDENCE_INCOMPLETE | 保存缺口；按本文件有限修复规则处理，不假装通过 |

Response直答：迁移了哪个成功实现；原方程/边界是否不变；MPI8/凝聚桥如何验证；两波长分别是否复现；p6/p4各有哪些因子；consumer与完整口径各省多少内存；总时间和Schur重复求逆成本；未过哪条Gate；全部新进程是否退出；为什么本轮停止。附简短可复现命令与证据表，不以“组件测试通过”替代完整案例。

建议普通commit顺序：最小BAL_H/侧区适配及tests；公开profile/dat和H2结果；H3与对照证据；最终response/docs。正式PDE使用clean源码SHA；最后修改后重跑受影响focused serial/MPI测试、Ruff/compileall和文档合同。没有运行full pytest/CI就明确not_run，不为无关文档改动重跑heavy。保留原失败，禁止amend/force-push/master合并。

原理参考：PETSc官方 [KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/) 与 [KSP operator/PC接口](https://petsc.org/release/manual/ksp/)。仅据其说明有限/非线性PC和原始operator分离原则，不要求升级本机PETSc到在线文档版本，不从接口合法性推导本候选收敛。

**任务到此为止：证明或否定“Task39extra成功的BAL_H机制，能否在13.5 nm和5 nm的Hybrid上下侧替代完整p6精确因子，并取得可信内存收益”。准确p4粗逆的可扩展替代、更短波长、更多模式、更细网格和任意非可分结构，均留待本轮结果审阅及用户下一次授权。**
