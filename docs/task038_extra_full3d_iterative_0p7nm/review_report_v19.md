# Task038-extra Review Report V19：历史 sweep 复核与真实结构优先的 PML 双向扫描检验

## 0. 身份、裁决和本轮要消除的 blocker

```text
repository                 = Rookie1234567/MyFEniCS
branch                     = codex/20260820-task38-extra-full3d-iterative-0p7nm
reviewed_HEAD              = af02330e23eafd395a3c5bba339701853a6026e4
base_master_SHA            = 438caf150439343ee7c4c58ad7e02a3da812a23c
review_date                = 2026-09-05
previous_review            = review_report_v18.md
previous_response          = response_v18.md
response_required          = response_v19.md
execution                  = continuous conditional batch R0 -> R1 -> R2 -> R3 -> R4
mandatory_stop             = terminal Gate or R4 closeout
master/default/merge       = unchanged / unchanged / NOT_APPROVED
full_0p7nm_PDE             = forbidden
```

最终目标仍是：约 2 TB 整机内存内求解 0.7 nm、周期单胞内任意非可分三维 Maxwell 问题。本轮首先消除的 blocker 是：**能否在原始 13.5 nm、p6/h10 真实散射问题上，用包含人工 PML 的高质量局部逆和双向扫描，取得有实用预算约束的完整求解，而不再只取得辅助问题或小 fixture 的 PASS。**

审阅裁决：V18 E1 按 `USER_AUTHORIZED_PERFORMANCE_CONTROLLED_STOP` 收口，未完成物理解；不追溯改成 numerical FAIL，也不恢复长跑。本 Review 前瞻性授权一个有限候选，不宣称 PML 必然有效。

用户本轮要求尽快判断真实结构是否可算。因此，取消“先完成多个小模型/多源/多 MPI campaign，最后才接真实问题”的顺序。**最多一个新最小 fixture 批次，随后第一场外层求解就是原始 p6/h10、1°、真实 RHS、零初值。** 不以单次 sweep 的 standalone contraction 作为禁止进入真实 FGMRES 的门槛。

只在本执行分支推进。R0–R4 条件满足时连续执行，不在每个子步骤等待 ChatGPT；失败则按真实原因收口，不自动转向其他 PC。

## 1. 历史复核：以前到底测过什么

下列内容是本次只读审查已核对的历史，数值均为历史 measured/derived，不是 V19 新结果。

| 历史对象 | 实际内容与结果 | 对新方案的约束 |
|---|---|---|
| T4 | 两 slab 的一阶 Robin facet action；p2/p3、h50、MPI1/2；没有外层 KSP/PDE | 不能称为 PML 完整求解试验 |
| T5 Candidate A | 已有真实局部 Maxwell shell、exact physical residual propagation、forward 0→1/backward 1→0；局部 GMRES 固定 restart/max-it=8/8 | 双向扫描和局部 physical 本身不是新发明，不得以此换名重跑 |
| A 的 physical RHS | 单次双扫 `rho=0.8145890334049838 > 0.60`；历史 process-tree peak `5,145,784,320 B`；外层完整 PDE 未运行 | 该负结果永久保留；一次单位步长修正不够好，不等于所有右预条件 FGMRES 都已失败 |
| Candidate B | 混合 Si–Si/Si–air 人工接口没有内部模态资格，未运行 | 不得用外部 Floquet 模态冒充非均匀内部精确传输 |
| Candidate C | fixed second-order local impedance，不是 PML；formal 在记录生成前于 `12,942,209,024 B` 触发旧 12 GiB watchdog | 旧 C 保持关闭；不得通过优化/改名重跑 C |
| V16 W0 | 实际接口 rank/count 和 simultaneous bytes 缺失；`W0_INTERFACE_RANK_CAPACITY_FAIL`；W1–W4 未运行 | 是证据/容量预审未闭合，不是已完成的 PML 数值失败；不得把 rank 上限当实际计数 |
| V18 E1 | checkpoint2024 的 residual `0.27299642739429014` 降至已保存 checkpoint3048 的 `0.15346927855972448`；RSS 采样峰值 `1,466,142,720 B`，swap=0 | 至少 1024 个 E1-local steps；TERM 最终步数/残差未知；E2/E3 未运行；不恢复数万步长跑 |

证据：[`sweep_oracle.md`](outcomes/sweep_oracle.md)、[`t5_physical_dual_authority.md`](outcomes/t5_physical_dual_authority.md)、[`transmission_family_closeout.md`](outcomes/transmission_family_closeout.md)、[`wave_aware_dd_preflight_v16.md`](outcomes/wave_aware_dd_preflight_v16.md)、[`response_v18.md`](response_v18.md) 及 [`V18 compact`](outcomes/records/restart64_physical_eventual_v18.json)。代码已核对 [`fullspace_sweep.py`](../../src/solvers/fullspace_sweep.py) 中的常量、local shell、局部 KSP 和 residual propagation。

结论必须准确：**已有 Robin 双向扫描负结果；本次已审查的 Task038-extra 证据中，未见“人工体 PML + 达到明确局部残差精度的逆 + 原始 p6/h10 外层完整 FGMRES”的同组合资格结果。** 这不是声称整个仓库、所有旧分支从未使用任何 PML。R0 仅对已有索引做一次增量核对；若发现完全同组合的历史试验，先复用它，不重复运行，不展开全历史重写。

## 2. 授权改变和保持不变的内容

| 项目 | V19 规则 |
|---|---|
| 精确外层方程、材料、原始几何、FE、Floquet、外部 Fourier-DtN | R1/R2 全部冻结 |
| PC 人工边界 | 从表面 impedance 改为有限厚度的局部体 PML；只用于 PC |
| 子域与顺序 | 一个固定四子域 z 分区；双向 multiplicative residual correction；无方向/分区扫描 |
| 高质量局部逆 | R1 允许局部 assembled/direct reference；必须达到 local explicit residual，而不是固定 8 步就视为合格 |
| 低内存版本 | R2 只允许一个有界的局部 matrix-free iterative 替换，详见 §7 |
| 小测试 | 只作实现安全检查；不作为真实结构能力证据 |
| 新粗空间、rank compression、CFS/shift 扫描、其他 Krylov family | 不授权 |
| 旧 Candidate C、V15 rank32、旧 p3 physical coarse standalone 路线 | 不恢复、不优化、不重跑 |

本 Review 只对 V19 新 profile 替代 V18 的“不得新建 PML/Schwarz PC”限制，并替代旧 T5/T6 的多源先验与单次 rho 前置 Gate。所有旧结果和旧阶段的 Gate 原样保留。R1 的诊断预算与 R2/R3 的低内存预算明确分开，不修改原 2 GB 资格定义。

## 3. 原始模型与输入身份

R1/R2 固定为原始真实结构，不降阶、不加粗、不缩域、不改入射角、不增加真实材料损耗。

| 物理/离散项 | 冻结值 |
|---|---|
| 结构 | rectangular block grating；period x/y=50/25 nm；z=-10…130 nm；宽 x=17 nm，宽 y=25 nm，高=120 nm |
| 材料 | air `n=1+0i`；grating/substrate Si `n=0.999002304859+0.00182649365i`；mu_r=1 |
| 入射 | wavelength=13.5 nm；grazing=1°；azimuth=0°；s；electric amplitude=1 |
| 离散 | complex128；Nédélec p6；h10；boundary-fitted hexahedra；full-space matrix-free |
| 边界 | x/y 双 Floquet；外部 z Fourier-DtN；沿用完整动态通道和 quadrature |
| 规模锚点 | historical algebraic storage rows=173802；不能把含 slave 的 storage rows 冒充独立 DoF |
| 历史模板文件 SHA256 | `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` |
| 历史 normalized checkpoint input identity | `754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f` |
| physical model SHA256 | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| ordered mode manifest SHA256 | `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` |

参考输入为 [`full3d_iterative_example.dat`](../../input/templates/full3d_iterative_example.dat)。新 profile/.dat 的 solver 配置不同，因此其 **actual input SHA 必须重新计算**，不能硬填历史模板 SHA。原始模型的 physical/mesh/mode identity 必须对齐；如 identity schema 有必要扩展，须保留旧 schema 身份并逐字段桥接，不能重新定义历史 hash。

正式 R1/R2/R3 均使用 `python scripts/run_case.py input/path/to/case.dat`。新增最小显式 opt-in adapter/profile；一 dat 一次计算。不得沿用模板的 restart20/max200，却在隐藏 benchmark 常量中静默改成另一套设置。benchmark 可管理 watchdog/checker，数值核心放通用 `src/`。

所有运行保存 input_original、resolved_config、run_manifest、actual input SHA、physical/model/mode/source SHA、run_summary、环境、MPI/线程和 artifact hashes。R1/R2 零初值开始，不依赖 checkpoint，避免“checkpoint 好看但 fresh 不行”的额外资格链。

## 4. 唯一候选的数学和工程定义

### 4.1 不改变精确物理问题

```math
A u=b,\qquad A=K_{\mathrm{curl}}-k_0^2 M_\epsilon+T_{\mathrm{DtN}}.
```

原始材料、负质量项、Floquet 和 streaming DtN 保持原样。PML 只改变 PC 的局部近似逆。不能给全局真实 A 增加吸收，不能用 PML 辅助残差代替 `norm(b-Au)/norm(b)`。

### 4.2 扫描算子：不夸称精确 Schur 或论文原算法的完整复现

本轮定义为 **PML-terminated multiplicative Schwarz double sweep**。它借鉴 PML 传输思想，不把一般 forward/backward correction 冒称 moving-PML block-LU 的完整复现。

`R_j` 将独立物理自由度限制到子域；`F_j` 把局部 dual residual 注入扩展 PML 空间；`E_j` 提取非 PML 的 primal correction；`D_j` 为基于共享自由度 multiplicity 的权重。所有映射均须明确 orientation、primal/dual、Floquet phase 与局部编号。

```math
\begin{aligned}
z&=0,\quad r^{(0)}=r,\\
B_j w_j&=F_jR_jr^{(q)},\\
\delta z_j&=R_j^H D_jE_jw_j,\\
z&\leftarrow z+\delta z_j,\\
r^{(q+1)}&=r^{(q)}-A\delta z_j.
\end{aligned}
```

访问顺序固定 `0,1,2,3,3,2,1,0`，一次 PC apply 共 8 次局部访问。每次都使用当前已更新 residual；禁止八个局部问题都使用原 residual 后相加并仍称为 multiplicative sweep。PC 返回 z，外层 right FGMRES 负责选择组合系数。

原式中的 `R_j^H` 表示匹配的代数 prolongation，不授权用实值 transpose 代替 Floquet 下的 Hermitian 关系。需满足物理自由度上的 PoU，PML 自由度不进入全局未知量。

### 4.3 冻结分区和 PML profile

R0 从原始网格实际 z facet planes 中，选择最接近 z=25、60、95 nm 的三个不同内部平面；等距时选较低平面，排序并记录准确坐标。四个非空 core，每侧一层真实 cell overlap；边界不足时取实际可用层并记录，不改变全局网格。

人工截断面外附加两层 PML cell，法向层宽沿用该侧相邻实体层；切向 mesh/高阶空间一致。PML continuation 仅在辅助区域沿法向延续切面材料分布，保留横截面非均匀性，禁止对真实 core 做平均化。碰到实际 top/bottom 时保留相应真实 DtN，不在真实外部边界重复加人工 PML。局部编号必须紧凑，禁止每个 slab 都持有全局尺寸 Krylov 向量。

PML 使用沿外向距离 t 的 quadratic stretch。先核实仓库时间因子和 outgoing convention。对 `exp(-i omega t)` / outgoing `exp(+i kz)`，正向形式为：

```math
s(t)=1+i\sigma_{\max}(t/\delta)^2,
\qquad
\sigma_{\max}=\frac{3\log(100)}{k_{z,\mathrm{inc}}\delta},
\qquad
k_{z,\mathrm{inc}}=k_0\sin(1^\circ).
```

这只把入射零级在理想均匀连续 PML 内的单程振幅衰减目标设为 0.01，**不是混合材料、其他 diffraction orders 或离散界面的误差保证**。反方向须按外向坐标处理，不得因全局 z 的正负让 PML 放大出射波。若约定不同，用已验证的相应符号，不做符号扫描。

采用明确的 Maxwell 坐标拉回。局部坐标 Jacobian J 的定义须记录；在拉回写法下：

```math
\epsilon_{\mathrm{PML}}=\det(J)J^{-1}\epsilon J^{-T},
\qquad
\mu_{\mathrm{PML}}=\det(J)J^{-1}\mu J^{-T}.
```

curl 项使用 `mu_PML^{-1}`，mass 使用 `epsilon_PML`；不能只给 epsilon 添虚部而漏掉 curl 度量，不能在材料变换中擅用 complex conjugate，不能双重施加 Piola/Jacobian。复材料完整保留。

1° 使法向波数小、所需 stretch 可能大，进而恶化局部条件数。这是本候选的明确风险，不是应当排除的“不好看案例”。不改成正常入射验证，不扫描 PML 厚度、sigma、shift、方向或分区。失效只关闭这一固定 profile，不证明全部 PML 方法不可能。

## 5. R0：最小实现检查，然后直接进入真实问题

R0 完成以下合并批次，不能扩展为独立多轮研究任务：

1. 核对 branch/HEAD/upstream/worktree、ABI/complex128、MPI1/threads1、资源、旧运行是否已退出；只重读变化过的 identity/证据，不重跑旧 V13–V18 campaign。
2. 新 PML/映射允许一个小 p2 fixture：检查 stretch=1 恢复原局部 Maxwell action、assembled/action 一致、primal/dual 映射与 PoU、反向 PML 的 outgoing 衰减、finite/input unchanged。action/mapping relative 目标 `1e-10`，PoU `1e-12`。不做 p2→p3→h50→多源→MPI2/4 层层 campaign。
3. 在**原始 p6/h10**建立实际 slab/PML rows、nnz、map/trace 数量与字节清单；允许无求解的 setup/symbolic analysis。未知量通过当前结构计数，不以“旧档案没有”无限等待 authority，不预设 rank512 就算通过。
4. 一个 prototype commit 连接 local action/inverse、outer solver、`.dat` 和增量 ledger，随后立即开始 R1。独立 checker 复用现有骨架，不新建几千行重复 orchestration。

实现检查不通过时不能运行错误 PDE；只修明确 bug，不改数学 profile 或容差。若关键实现问题无法在本轮窄修闭合，报告 `IMPLEMENTATION_BLOCKED`，而不是继续增加小测试阶段或宣称 PML 不收敛。

## 6. R1：原始真实结构，零初值，高质量局部逆

这是本轮第一场外层 PDE，不使用缩小几何、不从历史 checkpoint 起步。

局部 `B_j` 可显式装配并用 MUMPS 得到 reference inverse，仅在 PC 内；每次局部求解验证 explicit local residual `<=1e-10`，零局部 RHS 不除零。不能以 `DIVERGED_ITS` 或固定少量迭代冒充 accurate local solve。可复用已分解局部因子，但全部常驻因子、symbolic/numeric workspace 和编译进程均计入实测峰值。禁止全局物理 A/factor、全局 Schur factor、把各 slab 因子写盘后每次读取。

局部真实端口可使用与当前 DtN 等价的 auxiliary augmentation，必须记录所有额外 mode 自由度；不允许显式构造全局 dense DtN。R1 的 direct 仅是机制参考，不能升级为 0.7 nm production 架构。

| 外层设置 | 冻结合同 |
|---|---|
| 初值、RHS、A | 零初值、原始 physical RHS、原始 exact matrix-free A |
| 方法 | right FGMRES，restart64，max-it512，无参数扫描 |
| 数值目标 | full explicit true residual `<=1e-6` |
| 残差记录 | 每64步重算并落盘；终止时再显式重算；不只读 KSP reported norm |
| 求解预算 | 外层开始至终止最多7200 s，包含全部 PC/local solve/正交化/残差计算 |
| 完整流程预算 | precompile/setup/solve/release/postprocess/checker 最多14400 s；未完成即 performance controlled stop |
| 早期数值停止 | nonfinite、真实 breakdown、原始 operator/identity 错误；不因一次 sweep 的 rho>0.60 自动停 |

512 步和上述时间是本轮研究投入上限，不是数学不存在性判据。不得在跑到上限后自动追加几千步；也不得把“尚在下降”作为延长许可。

R1 必須跑出以下之一：真实全场数值 PASS；完整预算内未达到目标；局部逆不合格；资源/实现受阻。不能只交付 `PC apply PASS`。达到数值目标立即保存最终解并按 §9 恢复输出，不把“下一轮再接后处理”当作完成。

## 7. R2：仅在必要时做一次低内存真实模型替换

若 R1 已经完成完整 workflow、RSS<2 GB 且 swap=0，直接把它登记为**当前离散锚点的低内存原型**，进入 R3；不要为了增加阶段而额外重跑同一数值过程。它含局部 direct 时仍不得宣称 factorization-free 或具备 0.7 nm 可扩展性。

若 R1 数值和输出通过、但峰值在 2–12 GB，本轮只允许一次局部逆的低内存替换：保持同一 PML、partition、R/F/E/D、外层 A/b/restart/max-it，`B_j` 改为紧凑局部 matrix-free action，局部 right FGMRES restart16、max-it64、explicit residual目标 `1e-3`。辅助 PC 仅复用现有 positive p6→p3→p1 数值机制在局部网格上的版本；不恢复 standalone global physical p3 coarse，不改为新 HX/GenEO/Schwarz family。正定辅助系数与局部边界定义在 R2 第一次数值测量前写入 manifest，并与 R1 的真实 B 分开。

p1 development direct 仅可存在于受控小局部粗问题，必须报告 rows、factor bytes 和局部总工作集；不宣称未来可无限增长。任何局部 solve 未达到 `1e-3`，记 `LOCAL_INVERSE_NOT_QUALIFIED`，停止该 R2，不偷偷增加 inner steps。局部有限/误差/输入不变检验通过后，立即运行原始 p6/h10 零初值完整 FGMRES，预算同 R1，资源按 §8 的2 GB硬线。

R2 不另做一轮小 fixture campaign；同一真实模型的局部误差与 R1 correction 可直接对照。R2 不通过时必须区分“R1 机制有效、低内存近似退化”和“整个方法无效”。不自动再换第二种 local PC，不开始 response compression 或新的粗空间。

## 8. 资源合同：诊断参考与低内存结论分开

| 范围 | 警戒 / hard line，decimal bytes | 资格语义 |
|---|---|---|
| R1 高质量局部逆参考 | `10,000,000,000 / 12,000,000,000` | 本 Review 明确恢复原 task 的 diagnostic/development envelope，仅此 reference；超过2 GB不能称低内存通过 |
| R2 与 R3 | `1,800,000,000 / 2,000,000,000` | 完整 process-tree RSS 严格小于2 GB；不得用单 worker 或单阶段代替 |
| 所有运行 | swap=0；一次一个 heavy；可读 `/proc`；无孤儿进程 | hard Gate，不能因赶进度删除 |

诊断12 GB并非必须占用12 GB，更不是提高2 GB最终资格线。实际机器 `MemAvailable` 还必须至少留下 `max(4 GiB, physical RAM的10%)` 系统余量；取预设 cap 与实际安全上限中的较小值。记录本轮实际运行环境，不默认已迁移到2 TB工作站。

正式 factor 前做 local symbolic 与 simultaneous factor/workspace 容量预审；预测不足则停止，不靠 OOM 试边界。原始参考若无法在安全上限内启动，写 `REAL_ANCHOR_REFERENCE_RESOURCE_BLOCKED`；不退回小案例后宣称真实问题可行。

cold JIT、setup、solve、checkpoint、release、postprocess/checker 均受完整 watchdog。允许复用 source/form/ABI/hash 完全匹配的已资格化 cache以减少重复编译，必须如实标注 warm/cold及上游编译证据；没有本 profile 冷构建资格时不能宣称完整 cold-workflow <2 GB。仅缺冷构建资格时最多补做一次编译/setup资源测量，不重跑已通过的整个 PDE。

## 9. 结果保存、后处理与物理资格

每64步追加写 `cycles.jsonl`，每个周期至少包含 true residual、完整迭代坐标、外层 A 次数、8次局部访问/内层步数/局部残差、PC/orth/action耗时和资源。周期数据不能只留内存等 finally 才写。定期 checkpoint每256步；成功、预算耗尽或用户停止时，在安全边界额外保存最终/最后解与实际残差，非256整数倍也要保存。硬资源停止优先终止，不为写文件越过cap。

fresh run迭代从0开始；不沿用历史 origin1000。每次输出都绑定确切 solution hash。信号处理只请求在安全边界收口，不在异步 handler 中进行 MPI/PETSc 操作；父进程的强制资源终止仍有效。

数值通过后同一 workflow执行：保存最小 recovery packet → 销毁 outer KSP、局部 inverse/辅助层级与无用矩阵 → 记录 RSS下降 → 复用现有 recovery/postprocess。不得另起一个不计入资源峰值的进程来掩盖输出成本。

必须生成 complex E/H、固定 near-field samples、R/T/A、A_volume、能量闭合，以及同一12个significant identities的功率与复边界幅值：R/T分别取 `(0,0),(-1,0),(-2,0),(-4,0),(-5,0),(-7,0)`。外部 mode inventory不为满足该列表而改变；确无对应mode时显式标缺失，不补零。

能量检查使用 `abs(R+T+A_volume-1)<=1e-5` 和 `abs(A-A_volume)<=1e-5`；`A=1-R-T` 的恒等式本身不作为验证。有限性、被动介质符号/允许舍入误差和通道求和必须自洽。

已有 [`direct_authority_packet_audit_v1.md`](outcomes/direct_authority_packet_audit_v1.md) 明确：历史 scalar 参数对齐，但 exact canonical identity和 E/H、12+12 arrays仍缺失。scalar绝对差 `1e-5` 只作有边界交叉检查；未补齐identity不得升为full authority。不能为了本轮完整性重跑大型全局 direct。

若 R1/R2 都成功，对同一模型的 canonical E/H 使用相对L2 `<=1e-4`；R/T/A/A_volume绝对差 `<=1e-5`；选定12个功率绝对差 `<=1e-6`；复幅值整体相对L2 `<=1e-4`，近零通道另报绝对差。比较不得拟合整体相位/幅值。它证明 local-inverse替换一致性，不是独立网格收敛或独立物理算子验证。

输出成功但独立数组不足时，分类 `DISCRETE_NUMERICAL_AND_OUTPUT_PASS_AUTHORITY_LIMITED`，保留 `DIRECT_AUTHORITY_ARRAYS_MISSING`；既不把缺参考写成迭代场错误，也不宣布完整全场accuracy已证明。

## 10. R3：同尺度非可分三维挑战，不再缩小问题

只有原始模型取得数值、输出及当前2 GB资源资格后进入。使用同一外部尺寸、p6/h10 mesh、入射、材料集合和DtN通道；在原grating内加入一个明确的 cell-tag notch，打破原结构的 y均匀性和z挤出性。

冻结recipe：仅将原本为grating的cell中，中心满足 `x>0`、`abs(y)<period_y/4`、`40 nm<=z<80 nm` 的cell改为air。以单胞中心为x/y坐标原点。保存全部改变cell的canonical identity与实际边界；其余cell不改。若该原始网格上筛选为空或不能同时打破y/z不变性，报告fixture构造错误，不静默扩大区域或选更简单结构。

该case是明确标注的 **同尺度非可分材料分布挑战**，不是声称用户实际器件就有这个notch。按当前mesh离散定义，不宣称连续几何收敛。每个局部core都按完整cell tags构造，禁止用均匀截面或模态分离求解代替。

建立独立显式`.dat`及新physical-model/material-tag SHA，不能在不改身份的情况下覆盖材料。已有输入能力不足时，只增加支持该确定recipe的最小通用入口，不重写几何平台。使用R1/R2最终选择的同一profile，零初值、max512、相同时间预算、RSS<2 GB、swap0，并完成 §9 输出。

不为notch重新调PML/inner/restart/coarse。若失败，准确结论是“原结构通过，当前非可分challenge未通过”；不能以原结构PASS代替任意三维资格。R3成功也只证明这个非可分case，不证明所有结构或0.7nm。

## 11. 决策、执行规模和停止条件

本批次最多：**R1原始全场1次 + 必要时R2低内存原始全场1次 + 条件R3同尺度非可分全场1次。** 初值全部为零；没有单独checkpoint screen→同方法fresh repeat的重复链。

| 实际结果 | 结论与动作 |
|---|---|
| R0实现/原始容量被阻 | 保存真实blocker并结束；小测试PASS不能冒充候选有效 |
| R1在512步/预算内未达1e-6，且局部逆已准确 | 该固定PML/sweep候选未满足实用数值Gate；R2/R3不跑 |
| R1 local inverse不合格 | 不能评价传播机制；按局部实现/数值失败收口，不伪称PML失败 |
| R1通过且完整<2 GB | 跳过R2，直接R3；仍报告局部factor可扩展性缺口 |
| R1通过但>2 GB | 只进入一次R2；R1是诊断参考，不是低内存pass |
| R2失败 | 机制参考与低内存实现分开报告，R3不跑，不新增候选 |
| 原始通过、R3失败 | 不能称任意三维通过，完整保留非可分负结果 |
| R3通过 | 当前13.5nm两个case的离散/资源资格；accuracy/reference不足仍单列；不解锁0.7nm PDE或merge |

budget fail、numerical fail、resource stop、implementation blocked、authority missing必须分列。任何真实Gate失败不得通过降p、增h、缩几何、增损耗、减mode、换入射、改阈值或不断加迭代规避。

不要把 local-factor总工作量、外层iteration=1、derived bytes或KSP reported norm写成完整时间/内存/物理通过。当前1° near-grazing反射、内部异质性和PML条件数是预先承认的失败可能性。

## 12. 代码、测试、提交与交付

优先复用 exact split physical action、streaming DtN、owner-local mapping、fixed-restart core、checkpoint和release/recovery。旧 `fullspace_sweep.py` 的数值行为保持冻结；新通用模块只承载PML局部空间/逆和参数化扫描，不复制旧task runner。checker只读raw重算，不实现第二套求解器。

允许的最小变更：通用PC/local-PML模块、必要的`.dat` opt-in与nonseparable recipe、run_case adapter、增量ledger/安全退出/最终解保存、focused tests和本轮outcomes。禁止无关BLAS环境切换、全面MPI改造、历史目录清理和仓库级重构。

提交计划：

```text
1. feat(dd): add opt-in PML local inverse and real-anchor double sweep
   包含最小数学/身份测试、dat入口、增量记录；不拆成长测试项目。
2. evidence(task038): record original physical anchor PML sweep result
   R1完成或停止立即保存；通过则不等待review继续条件R2/R3。
3. evidence(task038): close real-first PML sweep qualification
   汇总实际执行的R2/R3和未运行项，最终response_v19。
```

每次改变相关代码后跑targeted tests、Ruff/compileall/diff-check；全Task回归在最终收口集中一次。不得在每个局部改动后重跑全仓或历史heavy。修正唯一明确工程bug时使用新SHA/新artifact root，保留旧失败；数学/资源负结果不得借“修复”名义重新抽签。

Git仅提交轻量证据。必须新增 `outcomes/pml_double_sweep_real_structure_v19.md`、对应 `outcomes/records/pml_double_sweep_real_structure_v19.json`、`response_v19.md`；更新 summary、test_summary、development_progress、development_model_registry。计划中的outcome名称此处不写成已存在的链接。

response至少回答：历史复用/差异；首场是否就是原始p6/h10零初值；实际PML/partition/inverse manifest；R1/R2/R3分别的true residual/steps/完整wall/RSS/swap；每次local精度与成本；所有输出与reference缺口；哪一类failure；局部direct/粗问题的扩展风险；精确HEAD/worktree和证据路径。

## 13. 方法依据与本轮审阅边界

参考原始研究：[Tsuji, Engquist & Ying, JCP 2012, DOI 10.1016/j.jcp.2012.01.025](https://doi.org/10.1016/j.jcp.2012.01.025)。该工作为Maxwell有限元moving-PML传播预条件提供依据，但使用局部直接求解；不能把其结论直接当成本仓库p6、双Floquet/DtN、1°和2 GB的保证。本轮定义是 §4 的固定multiplicative实现，必须由当前真实模型决定是否值得继续。

本次ChatGPT仅做远程文档/相关源码审查与本Review写入，未执行用户工作站PDE，未独立重算ignored raw。V18数据引用已提交compact及其hash-bound索引。所有V19数值、物理和资源结果目前为 `not_run`。

**最终执行原则：尽早在真正卡住的原始问题上完成一次有上限的真实求解判断；有效才压低内存并立即挑战同尺度非可分结构。不要用不断增加小测试或不断延长长跑替代这个判断。**
