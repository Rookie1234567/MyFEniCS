# Task041 Review V6：关闭传递一致性阻塞，交付优化后 5 nm 的完整结果

## 0. 决定、范围与执行身份

**本轮先不处理 node1，不等待双路硬件修复，也不启动 2 nm。继续在 socket0/node0 上完成准确 p4 单元凝聚迁移，解决 R3i3 的传递一致性失败，随后运行优化后的 5 nm / p6h4 / M480 / MPI8 完整 Hybrid consumer。交付重点是原方程与物理量通过、完整内存记录，以及是否在 24 小时内完成，不是再交一份仅有 tiny-FE 通过数的报告。**

```text
repository               = Rookie1234567/MyFEniCS
working_branch           = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date              = 2026-09-22
reviewed_base_SHA        = c0f55b02afa7c90a3729a6d9b137c1c591182069
base_latest_commit       = docs(task041): record R3 component and tiny FE gate
previous_review          = review_report_v5.md
latest_response          = response_v8.md
migration_commit         = 2ba8c891afb9a15095d38f7abc18879fa6a44d95
donor_reference_source   = b337d215c3d278d0c1e715f53e28b69f7f0ee3fe
new_batch                = task041_review_v6_transfer_and_5nm_24h
response_required        = response_v9.md
primary_execution        = socket0/node0, MPI8, one math thread per rank
formal_target            = W, 5 nm, p6/h4, M480 per direction
performance_target       = complete consumer wall <= 86400 s
elapsed_time_policy      = observe_and_report; not an automatic 24h kill
execution                = F0 -> F1 -> F2 -> F3 -> F4 -> F5
ordinary_default         = unchanged; explicit opt-in backend/profile
master_merge             = NOT_APPROVED
```

本轮消除的 blocker 是：**已有低内存准确逆迁移被未定位的共享自由度一致性检查挡住，正式入口尚未接入，也没有 5 nm 的完整速度证据。** 长期目标仍为 0.7 nm、任意非可分三维周期单胞、约 2 TB 整机；本轮是 Hybrid 求解器实现与性能资格，不是任意三维或更短波长资格。

用户本轮覆盖 V5 的硬件先行、双路对照和 2 nm 扩展顺序。R1/R2 硬件工作暂停但不改写负结果；V5 的 2 nm 个位秒条件不再是本轮 5 nm 的前置门。继承 Response V8 记录的单路执行和不设严格 elapsed-time stop：24 h 是性能判定，不可擅自转换成超时强杀。保留数值、资源、安全停止及用户随时停止权。

本次 ChatGPT 只新增 review，没有实施修复、运行 PDE 或操作工作站。Codex 应基于当前真实工作树执行；若远端已有新提交，先读差异，禁止 reset 覆盖本地工作。

## 1. 此前能解、这次失败：已经确认什么，尚未确认什么

证据以 base SHA 固定：E1 为 [Response V8](response_v8.md)，E2 为 [凝聚迁移 record](outcomes/records/task041_v5_condensed_speed.json)，E3 为 [原正式 BAL_H 结果](outcomes/side_balh_transfer_v1.md)，E4 为 [共同布局结果](outcomes/common_layout_equivalence_v4.md)。

| 对象与范围 | 事实及单位 | 本轮判断 |
|---|---|---|
| R3i3 MPI8 tiny-FE | bottom/full/Q 的候选绝对差 1.3116919128020489e-11，限值 1e-11 | 超出 3.1169191280204895e-12；定位在 P 的候选一致性，不是最终场误差 |
| 同次 p4 求解 | 原 A4 相对残差 6.795828778707217e-11 <= 1e-10；一次回代、零 refinement；粗 RHS 范数 1087.8641826196488 | p4 residual 通过；RHS 范数不是失败候选行的数值尺度 |
| 未到达的代码 | cell_condensed、完整 PC、side.apply、top 均未运行 | 不得归为新凝聚后端不收敛，也未发生侧区迭代超限 |
| R3i3 资源 | tree peak 4636389376 B；worker rc1；unit wall 68.728670 s；swap 0 | 资源门未触发；不是 OOM、node1 导致的已证实错误或人工中止 |
| R3h6 serial/MPI2 | old/new Q、PC 差约 1e-13，四项原 A4 检查通过 | 接受已有小组件正证据，不外推到 MPI8 |
| 原 5 nm H3 BAL_H | source 51694bbc49d90e70eef87c953f07c695f5fc519c；worker wall 191662.819902868 s，约 53.24 h | 原数值/物理通过；公共全过程资源/退出历史缺口仍保留 |
| 原 5 nm H3 exact-side | source db07f1cfb34f0135f636fa96a0a37b29a3a2969b；有完整场与通道参考 | 主要离散数值 authority，禁止为本轮重跑整个旧 exact/PDE 基线 |

### 1.1 本次不是原 5 nm 正式输入的重跑

当前测试 `src/test/test_347_task041_balh_mpi8.py` 调用 `_fixture_config(6, condensed=True)`，然后设 `mesh_axis_cell_counts=(4,2,2)`、内部接口 0.5，每侧实际 8 个单元、8 个 rank 各有 owned cell。被引用的 fixture 位于 `test_347_task041_balh_physical_operator.py`：波长 3.7，单胞 1×1×1，复折射率 1.4+0.02i / 1.7+0.01i，非零双 Floquet，手工外部模式；不是 W/5 nm/p6h4/M480。

输入还由 `_fill_active(source, 1.25)` 按全局代数行号增长，再用原侧区 action 生成 `rhs=D*source`；第一次 Q 实际作用于注入的 `source`，不能混成 Q 正在求这个 manufactured rhs。MPI 分区/编号、几何、材料、列输入和数值尺度均与旧成功案例不同。过去的 MPI8 正式成功与本次 fixture 失败不构成直接矛盾，但也不能免除对真实实现缺陷的调查。

### 1.2 最有价值的三个待判方向

当前 P 按单元计算 `T_e*c_e`，向 fine owner 路由多个共享行候选，选择 canonical candidate 并检查全部候选。legacy 与 batched resolver 都以**未经归一化的最大绝对差**和固定 1e-11 比较。此门对输入幅值不具有尺度不变性。

需区分：候选路由/ghost/MPC/方向或对象所有权错误；高阶局部插值/方向变换的舍入或结构零泄漏；固定绝对门与该输入尺度不相容。仅因偏差小不能选第三项，仅因 MPI8 才失败不能选第一项。**共享 p4 系数在数学上即使只是近似解，也应表示一个相容有限元场；不能把 p4 residual≈1e-10 自动当作共享行不连续的合理解释。**

## 2. F0：单路隔离与最小现场核对，不再排障 node1

先读根/目录 AGENTS、仓库工作原则、task、最新 review/response/outcomes。原 task 的 MPI1/exact-only 已被后续 review 覆盖，本轮以这里的 MPI8/BAL_H/准确凝聚路线为准。使用原生 Ubuntu canonical `/home/fenics/Projects/MyFEniCS`，在同一 shell 激活 `.venv/bin/activate_myfenics_native.sh`；ABI 失败不得继续 pytest/PDE。保留当前 BIOS、风扇与内存档位，不重启、不拆内存、不改寄存器、不跑 node1 压力或双路比较。

保持总 MPI8×1，核对实际物理 topology 后使用现有 socket0 CPU1–8。单纯外层 `numactl --membind=0` 不作为子进程生效证明。检查 public wrapper、service、MPI daemon 与实际 rank 的继承；必要时通过已有每-rank 启动钩子在启动 Python/分配大数组前设 node0 策略。正式 preflight 至少记录实际 rank affinity、task mempolicy、首触的私有计算页、p4 ready 后及首条响应后的 private-page 节点分布。

`numa_maps` 的某个 VMA 显示 default 可以回退 task policy；不能仅凭 default 就判未绑定，也不能仅凭命令行就判已绑定。共享库/文件页在 N1 不自动等于大计算数组越界。使用有界、低频抽查，不持续扫描数百 GB smaps。只有实际 node0 计算存储资格通过才作性能对照；故障不能未经证明归给 node1。

保留一次一个 heavy、swap=0、系统及 node0 余量、disk、watchdog、PID/starttime 清场要求。不杀邻近 Full3D 或改变其 affinity；邻 heavy 活跃时暂停竞争型性能测试，但可继续编辑和轻量离线检查。保留全部旧 QEP 和负结果，旧 D1e 已终止，不再发送停机信号。

## 3. F1：一次有信息量的复现，先保存失败输入，再修复

### 3.1 最小诊断对象

优先读取 R3i3 旧 raw stdout 和 source/hash。若没有保存候选行数据，允许在原 MPI8 fixture 上做一次定向复现，保持原 source seed、物理、分区条件和 full backend；不先改 RHS、降阶、改容差或转回 MPI2。保存以下**有界、可离线重放**的数据后再抛异常：

- 最坏行及少量代表共享行的 fine global id、实体/局部位置、cell global id、owner/source rank、方向/permutation；rank 的 owned/ghost/active 摘要在 Q 之前输出。
- 原复数候选值、canonical 值、绝对差、候选本身幅值；相应局部 `T_e` 行和 coarse coefficients、coarse owned/ghost id 与相关 MPC master/phase。
- 原 full p4 返回向量的有限分片或 tiny-FE 完整分布式向量、范数、p4 audit、source/config/library/transfer identities；不依赖事后从日志重造分区。
- 同一接收 packet 给 legacy/batched resolver 的结果；比较解析逻辑时不重复求逆。捕获须保留 collective 顺序，不能让一个 rank 异常退出、其他 rank 卡在 allreduce。

原 `_candidate_packet` 只传 ids/values，缺 cell 身份；允许仅在诊断模式中增加小型 provenance 或重建失败行关联，不给每次正式 P 全量通信永久增加大 payload。正常正式过程仍有原一致性检查，只不重复输出庞大审计包。

### 3.2 定位顺序及最小修复

| 层次 | 对照 | 决策 |
|---|---|---|
| resolver | 同一已保存 packet 走 legacy/batched | 不同则修解析；相同则不把 batched 函数名当根因 |
| coarse 输入 | 同一共享 coarse DOF 的 owner/ghost、MPC处理前后、输入未修改 | 不一致则修同步、映射或相位；不是放宽门限 |
| 单元映射 | Basix元素/variant、实际方向、局部到全局索引；相邻单元共享实体的作用 | 修明确的方向/编号错误；不得只按坐标排序Nédélec DOF |
| 数值结构 | 拆分该共享实体应依赖的 coarse 支撑，与应严格为零的其他实体/内部贡献 | 检查高阶插值表的结构零噪声是否被内部大系数放大；不是预设该原因成立 |
| 求解路径改变 | 旧成功source与当前full路径的相关diff、借用对象被改写与否 | 修真实回归；旧名字full不证明代码逐字不变 |

优先保持原 1e-11 门不变，用数学等价的实现修复。例如在**独立证明实体支撑**后构造对应 trace/edge/face 插值块，避免非相关内部自由度数值泄漏；不能直接把所有小于某个阈值的矩阵条目置零。保留全部合法 p4 多项式的插值再现，并覆盖复数、两侧、所有相关方向及 Floquet。P 改动时 P^H 必须来自同一线性映射与owner语义，不能只改 P 而留下旧伴随。

### 3.3 若证据只支持舍入与尺度敏感：本轮允许怎样关闭

不直接把 `ROW_CONSISTENCY_LIMIT` 改为1e-10，也不归一化测试输入后删除原失败输入。可以把缩放输入作为诊断，至少保留原输入及有限的较大/较小实数和复数缩放；线性缩放只能说明尺度行为，不能独自证明没有实现bug。

对局部点积，可记录以下操作尺度与舍入模型：

```math
v_i^{(e)}=\sum_j T_{ij}^{(e)}c_j^{(e)},\qquad
s_i^{(e)}=\sum_j \lvert T_{ij}^{(e)}\rvert\lvert c_j^{(e)}\rvert,\qquad
\gamma_m=\frac{m u}{1-mu}.
```

`m` 必须按实际复数乘加/变换计数，`u` 是所用浮点精度；表系数构造误差、方向变换及数据误差需要另外估计。`gamma_m*s` 仅是解释一段运算的工具，不是整个 FEniCS 流程的自动严格上界。需要时可对这个小局部行使用独立高精度 oracle，不能把生产 PDE 变成混合精度或增大常驻内存。

**仅当映射/约束/同步正确、原失败行的偏差被事先固定且独立验证的误差包络解释、有限元 oracle 与 P/PH/Galerkin 全部通过时，允许在显式研究profile内增加 scale-aware roundoff 判据。** 保留旧原始绝对差和 `legacy_absolute_pass=false`，另记新策略/公式/参数/source与资格；这属于本review明确授权的诊断语义修正，不把旧失败改为PASS。包络常数不能反向拟合为“刚好大于1.31169e-11”，不能用全局大范数掩盖局部错行；测试必须拒绝错owner、符号/phase、陈旧ghost和非有限值。普通默认仍沿旧策略，直到后续最终审阅。

独立 P/PH 与数学 oracle 的作用尺度误差保持 <=1e-11，dot/Galerkin 与原空间约束门保持至少原1e-10等级；最终 p4、侧区和Hybrid精度门完全不动。包络无法闭合、结构性误差仍存在或只能靠降低精度才能通过，则停止该路径并给具体证据，不能伪装成已修复。

## 4. F2：完成 MPI8 准确凝聚资格，再接入正式入口

**准确 p4 单元凝聚只换求逆的组织：局部消去内部量、解较小的trace/端口系统、回代完整 p4 修正。它不是用更弱的近似逆换速度。** 必须保留一般非零内部/端口 RHS、消元后的端口修正、原 p4 独立残差；p6 已经凝聚，不重复实施另一套 p6 消元。

```math
S_4=A_{rr}-A_{ri}A_{ii}^{-1}A_{ir},\qquad
\widetilde g_r=g_r-A_{ri}A_{ii}^{-1}g_i,\qquad
S_4y_r=\widetilde g_r,\qquad
y_i=A_{ii}^{-1}(g_i-A_{ir}y_r).
```

F1关闭后，运行原MPI8节点完成 bottom和top的 old/new Q、完整BAL_H、真实side.apply。保留serial/MPI2已通过证据，只对受影响模块跑targeted tests，不为文档变化重跑昂贵资格。full与cell_condensed顺序构建，释放旧factor后再建新factor，借用的p6 mesh/MPC/layout与RHS不变；不要同时保留两套大因子。小向量可留作比较，全部所有权/释放先验查清。

| Gate | 要求 |
|---|---|
| Q 旧/新作用 | 现有 MPI8测试相对门 <=1e-11；零输出另看绝对差 |
| BAL_H PC 旧/新作用 | <=1e-8；输入不改，有限，方向/约束通过 |
| 每次准确 p4 逆 | 原 A4 相对残差 <=1e-10；已有有限 refinement 如实计成本；不增加新内层迭代PC |
| 每条 side.apply | 原侧区 explicit residual <=1e-2、KSP reason合格、zero start、restart32/max128 |
| 响应强比较 | e_x/e_A沿原1e-8诊断门；超出时查解算路径/阈值敏感性，不凭两边都到1e-2自动放行 |
| 所有权 | owned/ghost/empty-owner和MPI约束检查；原action/RHS未变；清场通过 |

不要把 donor Full3D 的564→112步或2.8GB/约25min搬成Task041的预期值。本轮 p6侧区原本就在trace空间；p4准确逆等价时主要收益应看factor、回代及局部恢复的净成本，迭代数必须实测。

当前 `cell_condensed`尚未接到正式runner。资格通过后，做最窄接线：从一个显式新case/profile把backend经注册、resolved_config、worker入口、factory传到bottom/top；保持ordinary full默认不变。保存 requested/backend实际值、p4 retained rows与factor库存，检测两个侧区都用了cell_condensed，拒绝未知profile或silent full fallback。不能只在pytest里切换后端却声称正式计算已优化。

## 5. F3：冻结 5 nm 身份，先一个短回归，再直接进入真实尺度

正式目标继承 E3 的H3，不从3.7nm fixture或donor Si复制物理参数：

```text
wavelength             = 5 nm
material               = W / tungsten
n_substrate, n_grating  = 0.99396854453 + 0.00435380777 i
geometry               = original 50 x 25 nm periodic cell, z=-10...130 nm
side interfaces        = z=10 nm and 110 nm
FE / mesh              = p6 Nedelec, structured hex, h4, original actual grid
internal modes         = M480 positive + M480 negative; 960 modal coefficients
external DtN           = original auto_propagating inventory, complete physical keys
MPI / math threads     = 8 / 1; socket0/node0
outer                  = original right FGMRES, restart32, max2048, zero start
inner                  = right FGMRES32, max128, rtol1e-2, zero start
p4 inverse             = qualified exact cell_condensed, original A4 gate1e-10
propagation/traction   = full3d_uniform_cg / full3d_one_cell_exact_schur
```

完成一次受影响的13.5nm/p6h10/M120/MPI8完整Hybrid回归，与既有H2参考比较；它只证明接线和恢复正确，不证明5nm速度。若相同最终源码/相关hash的该回归已完整通过则复用，不重复运行。

随后在真实5nm两侧做既有固定八RHS配对：bottom `207,15,671,493`；top `310,12,666,493`。小fixture的 `_fill_active` 不能替代这些真实模态激励。同一side/layout顺序比较full与cell_condensed，所有调用计费；不拿跨fresh布局的数组直接相减。

先分解一次响应中的实际时间：P^H、p4 MatSolve、local reduction/recovery、A4原残差、P、A6体/DtN、H6、约束/通信/正交化。父子inclusive区间不得重复相加；每rank最大值之和不是端到端wall。setup、首次作用、稳定作用和日志代价分开。

准许至多两组**由5nm实测热点决定**的等价优化：优先缩减/恢复批处理、避免重复局部装配和临时复制、固定索引/基函数复用、编译循环、bounded tensor action或DtN批量作用。保留现有成功的transfer优化，不强制重写全部kernel。每组先做动作检查，再复测受影响的固定响应；不要无休止增加candidate/预检查，不能为凑目标换成弱Schur、recycling、神经网络、GPU/双路/MPI16、BLR、低精度或p6全局LU。

如果准确凝聚减少factor但未减少总时间，必须说明局部恢复/A4检查等净成本；不能只报factor变小。若迁移后新增原p4/PC缺陷则先修相应缺陷，不自动退回full跑完并称迁移成功。

## 6. F4：正式 5 nm 完整运行是本轮主要交付

在F1/F2/短回归及真实5nm组件数值、资源Gate通过后，**明确授权连续进入一场新5nm完整consumer，不再为每一小步等待用户确认**。不要把2nm原来的重复样本失败、CPU1硬件未修或donor其他波长资格当作本轮重新立项的条件。

优先复用已有**对应5nm**的QEP packet，按当前validator核对全部identity与分片；禁止用已保存2nm packet替代。producer/consumer source分别绑定，kernel/backend改变不自动使同物理packet失效。packet缺失或真实不兼容时，报告具体失败项；不伪造summary，不自动重求QEP或重跑旧exact/full consumer。目标是一个新的 `.dat`只代表一次正式计算，通过 `python scripts/run_case.py <case.dat>` 及既有service启动，避免嵌套mpiexec。

执行完整阶段：packet load、两侧构造、原模式Schur、外层、原真实残差、最小recovery packet、release-before-recovery、复数E/H、R/T/A/A_volume、全部衍射与公共清理。生产backend在日志与最终summary中实读，而不是由文件名推断。

**不要为了比较而再次跑旧53h BAL_H基线。** E3保留历史时间/数值；同布局八RHS提供当下实现的配对证据。硬件/内存档位改变时，历史全流程时间比只能称描述性比较，不能把全部收益归给软件。

### 6.1 Schur重复检查与此前2nm问题分开

保留5nm原repeat Gate，不因旧2nm重复差4.4e-5就提前放宽，也不把本次P共享行门与Schur重复门混为一谈。若出现repeat失败，先保存小型first/second样本矩阵、分侧差异、column identities和对应内层计数，再抛异常；这些数据很小，不需要保存所有FE响应。仅有同一输入残差均<=1e-2不能证明重复一致。

属于明确工作区/输入修改/同步缺陷时按最小修复恢复受影响资格；根因不明时保存数据并停止，不以“FGMRES允许不精确PC”为由跳过原action正确性和重复门。不得为取得一次完整结果而继续错误系统。

### 6.2 24小时目标与实际速度判定

```math
T_{5,\mathrm{consumer}}=T_{\mathrm{public\ launch\ to\ finalizer\ completion}},\qquad
\mathrm{target}=86400\ \mathrm{s}.
```

计入packet读取、setup/预处理、原监督流程内的准入检查、完整Schur、外层、恢复、物理核验和清理；worker时间另列，不能只算KSP或从Schur开始计时。历史producer成本与fresh-equivalent总时间另列，复用QEP不能冒充fresh workflow都在24h内；开发/回归累计成本也单独披露。

原worker191662.8199s约53.24h，达到24h至少要约2.22倍整体速度、减少54.9%耗时；此前约26.6%的组件降时不等于本目标已达成。5nm有1920条正式侧区响应：即便忽略一切其他费用，24h只提供平均45s/响应。此算术用于辨认瓶颈，不硬设单条响应或迭代的短timeout。

F3输出带假设的总时间规划，考虑两侧、难易样本、setup/outer/recovery；固定8项是有意选取的样本，不作无偏ETA。规划用于选择最多两组热点，不要求先“预测必然<24h”才准许运行，否则无法取得真实结果。数值与资源合格的首个最终候选应进入上述一次完整验证。

**24h是报告目标，不是本轮新增的强杀线。** 若到24h仍未完，记录 `TIME_TARGET_NOT_MET_AT_24H`、真实阶段、已完成列数/比例、吞吐和带假设剩余工作，不重启、不归零计时；有正常进展且数值/资源安全时继续这一场以取得最终物理解。用户中止、资源/数值失败、实际死锁/无进展按原保护规则处理；不能用observe_only授权额外反复长跑。完成后明确 `NUMERICAL_PASS_TIME_TARGET_MET` 或 `NUMERICAL_PASS_TIME_TARGET_MISSED`，失败/中止则独立分类，不编造RTA。

## 7. 必须保持的数值、物理与资源合同

| 类别 | 5nm最终门或边界 |
|---|---|
| reported/global/bottom/top/modal residual | 各 <=5e-9，以原完整Hybrid方程独立重算 |
| projection / 两侧traction / external-q | <=1e-8 / <=1e-8 / <=1e-10，原法向/相位/归一化 |
| 每次原p4 inverse | A4相对残差<=1e-10；finite、refinement与回代计数 |
| R/T/A_balance/A_volume 对E3 exact | 各绝对差<=1e-8；不可仅比较R或守恒 |
| selected complex E/H | relative L2各<=1e-6，固定坐标/material/key，不作phase fit |
| canonical trace/full | 原相对门<=1e-5，物理行键/布局对应已证明 |
| significant diffraction | 两边power>=1e-8的并集；complex amplitude与power相对差<=1e-6；全部弱通道也输出 |
| normal flux | 原relative<=1e-4 |
| 守恒与体吸收 | 原abs(A_balance-A_volume)、abs(R+T+A_volume-1)各<=1e-5 |
| 内存 | 既有严格simultaneous tree cap 53221163008 B不提高；资源profile中的更严上限继续适用 |
| 节点与主机余量 | 依据node0实际可用量和模型峰值预检；继承V5系统reserve要求，不把整机2TB当node0容量 |
| swap / OOC | job swap=0、新增global swap/pswp增量0；既存global基线独立披露；无OOC/BLR/隐藏低精度 |
| 生命周期 | 精确unit/PID/starttime、整树/稀疏PSS/USS、公共finalizer、compiler/原生workspace均入账 |

不得以原H3不完整的RSS峰值推导稳定节省比例。完整新峰满足cap，且同scope比较才谈“不增加/降低内存”。少量组件分侧测量不能代替正式双侧峰；两个大p4后端不得同时驻留。保持原factor依赖的源矩阵寿命，不做未经后端验证的early free。

## 8. 交付顺序、停止和避免任务再次停在脚手架

| 阶段 | 必须产物 | 后续动作 |
|---|---|---|
| F0 | 实际CPU0/node0/ABI、工作树/排他证明 | 单路通过就继续；不等node1 |
| F1 | 失败行可重放证据、根因或明确数值解释、最小修复、负例测试 | 通过后直接MPI8，不再只报failed |
| F2 | 两侧old/new Q/PC/side.apply，backend正式接线 | 参数传递和实际factor库存通过 |
| F3 | 一次必要13.5nm回归、真实5nm八RHS与热点净收益 | 至多两组等价热点后固定最终source |
| F4 | 一场优化后5nm完整consumer | 原残差/物理/资源通过；记录24h达标与否 |
| F5 | response_v9和统一结果表 | 推送原执行分支，停止等待最终review |

允许有证据的局部实现修复连续推进；每个已定位根因修复后只重测受影响最小节点，不能每次修一个日志字段重跑全套或QEP。新增正式大运行最多一场成功目标运行；若它因明确实现事故早停，至多一次受影响重试，保留失败成本和runroot，累计费用不得隐去。真实数值/资源失败、缺合法packet、无法隔离node0或故障根因未闭合时，交具体blocker，不无限扫描参数。纯未达到时间目标不是数值失败，也不以新full后端冒充cell_condensed完成。

建立普通提交序列：定位/最小测试；传递修复；凝聚正式接线；最多两组热点等价优化；clean source运行；结果/Response V9。若采用主控—执行双窗口，其内部审阅仍按AGENTS，但不要求用户逐条重复授权。不得修改旧task/review、旧负结果或合并master；不用amend/force-push，不整分支迁移donor。

中心交付建议为 `outcomes/transfer_fix_5nm_24h_v6.md` 与一个小型 `outcomes/records/task041_v6_transfer_5nm_24h.json`。更新summary/test_summary/development_progress/development_model_registry。沿用现有ledger新增V6阶段记录，不创建竞争账本；原始数组/log放ignored results，Git只存可复核compact。

Response V9开头必须回答：**为什么旧成功与这次失败能同时出现；首次分歧究竟在哪层；改了哪几行数学实现或诊断语义；新后端是否真的进入完整5nm；最终R/T/A/A_volume和E/H是否通过；完整wall/Schur/outer/setup分别多久；24h是否达标；两侧每步/每RHS/迭代数与峰值如何；还有什么未完成。** 禁止把预测、tiny-FE或8RHS结果写成完整5nm成功。

## 9. 审阅依据与可复核入口

本轮依据base下的根/文档AGENTS、仓库工作原则、既有task与最新review/response/summary、迁移compact，并直接核对E5/E6代码。E7是继续实施时必须核对的完整逆/入口定位清单，不冒称已执行这些代码。task的blob身份与已读版本相同；任务根目录未新增独立补充任务书，不从旧聊天推断后续资格。

| 依据 | 文件 / 用途 |
|---|---|
| E1–E4 | 本文§1的结果入口；所有数值是旧记录，不是ChatGPT新运行 |
| E5 | `src/test/test_347_task041_balh_mpi8.py`、`test_347_task041_balh_physical_operator.py`：实际fixture、输入及old/new顺序 |
| E6 | `src/solvers/physical_balanced_same_mesh_transfer.py`：Basix局部插值、方向、候选路由、绝对一致性门 |
| E7 | `src/solvers/physical_balanced_side_inverse.py`、`physical_balanced_physical_operator.py`、`p4_cell_condensed_inverse.py`：实际backend/完整逆接线；实施前继续核对当前函数 |
| 治理 | `AGENTS.md`、`docs/AGENTS.md`、`docs/repository_work_principles.md`、`docs/markdown_rendering_standard.md` |

外部primary资料只解释方法，不替代当前ABI或仓库实测：

- [Basix 0.10 插值与实体/方向接口](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.interpolation.html)：元素间插值与方向变换；结构零处理必须由这些数学实体关系证明。
- [PETSc FGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)与[KSP手册](https://petsc.org/release/manual/ksp/)：不精确PC与原方程残差分离；不证明任意PC必收敛。
- [Linux NUMA memory policy](https://www.kernel.org/doc/html/v6.7/admin-guide/mm/numa_memory_policy.html)：task/VMA政策继承与bind语义；实际rank需自行核验。

本review的Markdown应做围栏/表格/链接检查和可用的渲染检查；无法核实GitHub页面视觉效果时如实注明。本文不宣称当前失败已修复，不宣称24h能够预先保证，也不批准合并。
