# Task40extra Review V23：完成原尺寸端口作用，以真实支撑和吞吐推进 2 TB / 48 h

## 0. 审阅结论与本轮行动

**V22 有实质性的原尺寸进展，应继续沿现有方法推进。** 原尺寸 p6 有限元空间和全局周期约束已经建立；18,968 个模式已经对各自一侧的全部 2,176 个边界面完成生产 Bα/Dx 作用。它不是只在两个局部单元上重复扫描。任务进程树 RSS 峰约 3.24 GB、专用 cgroup 峰约 3.53 GB，任务 swap 为零；本次停止来自固定工作窗口到期。[R1]、[R2]、[R7]

目前最有价值的下一步，是在同一原尺寸对象上**减少每个模式的全域数组扫描，并查明端口实际耦合到哪些自由度**。这两件事分别回答 48 h 和 2 TB 的关键问题。继续只报小模型迭代次数，或只补完剩余模式而不统计实际支撑，都不能充分回答这两个问题。

| 审阅决策 | V23 行动与边界 |
|---|---|
| 接受 V22 原尺寸 FE/MPC 和全边界作用前缀 | 保留 18,968/32,060 的真实结果、失败尝试和时间停止分类；限定独立数值资格范围 |
| 唯一主线 | 紧凑边界工作区 → 全模式 Bα/Dx 与真实内部/边界支撑库存 → 原尺寸参考预条件器真实 q 映射下的有界矩阵块 |
| 最重要的内存决策 | 全模式逐一测量 B、D 的内部支撑；若确实为空，直接消除相应内部端口缓存；若不为空，按实测数量保留 |
| 预条件器 | 沿用 p6 reference、`ROW_TILE_BOUNDED_CSR_V17`、`ONE_Q_REFACTOR_V19`；本轮改善已有方程的表示、接线与成本 |
| 小模型 | V19 最小退出资格继续有效；本轮不把再跑同一缩小 PDE 或 E2 当默认前置条件 |
| 下一轮独立工作包 | 最多 6 h，含实现、验证、运行和收口；具体登记见第 8 节，旧 V22 窗口和费用保持原样 |
| 审阅状态 | 阶段进展 `PASS_WITH_QUALIFICATIONS`；最终原尺寸场、2 TB / 48 h、精度资格仍 `NOT_QUALIFIED` |

通俗地说：B 把边界模式的系数变成作用于有限元方程的载荷；D 从有限元场中提取相应模式量。知道它们实际触及哪些行，才能决定哪些大数组真正需要保存。q 是现有周期参考预条件器使用的相位子问题；真实非可分目标的物理算子仍需单独保持完整，不能因为参考问题有八个 q 就宣称目标已解耦。

## 1. 审阅身份与证据范围

| 项目 | 本次核对 |
|---|---|
| 仓库 / 分支 | `Rookie1234567/MyFEniCS` / `task40extra_0p7nm_engineering` |
| 冻结结果 HEAD | `084270e06f7a2c4d4e540ed839c7584d82fe32af` |
| HEAD 时间 / 说明 | `2026-10-10T08:34:35Z` / `docs(task40): close V22 original-size generated-port probe with partial evidence` |
| V22 正式运行 source | `ae3f1a4bc557170dc9af51669139683a8ab032a5` |
| 上轮 Review V22 HEAD | `c2ec1e87cbbc88ba568537d6d1d591d76794611e` |
| Review V22 → 本次 base | 9 个提交、34 个变更文件 |
| 正式 run ID | `task40extra_0p7nm_target_original_ny8_operator_probe_v22` |
| raw run root | `results/task40extra_nonseparable_0p7nm/task40extra_0p7nm_target_original_ny8_operator_probe_v22__full3d_iterative__mpi1__Mna/20261010T070935.463004Z` |
| 运行输入 SHA-256 | `33cb569eb900f60100569a6659138589a9d26784a22e05d50c7fe63190bac4ff` |
| 运行 physical-model SHA-256 | `ea3bc109992cabeae2f13e6adc5d3eb779fb92a2c75dcd355426e88957680241` |

本次读取远程 response、operator/inventory/tests/controller compacts、run index、摘要、输入和实际 solver/worker/service/checker 源码；复核远程文件内容 hash，并以源码检查结果的真实作用范围。大型 NPZ、原始 timeline 和本机运行目录未在本次远程审阅中重新执行或下载核算，其实测数字来自已提交、绑定身份的回执及主控读回记录；本报告不会把这种审阅写成独立重跑数值 oracle。[R1]–[R12]

运行输入 hash 与 tracked 模板文件字节 hash 是不同口径。后者为 `b00aeca7d9ef59697ac2d339035126644f23429c818f25a322b9e095628c565a`；模板还保留 preflight/未授权缺省值，实际阶段和授权由正式运行配置绑定。不得把两个 hash 混用。

发现一处轻量索引漂移：本次两次回读的 `response_v22.md` 实际 SHA-256 为 `ded69e2f44c31ca2e4c82b00cfd66b708a862accf29f2206f0552e9785f5d5b5`，run index 仍记较早的 `15d3113e2e0fe40af692a540817e4ade5d981c47d368fcb50072c0063fab8247`。三份结果 compact 与 checker 源码 hash 均匹配。下一轮收口刷新当前索引、标清快照时间即可，不据此重跑模式扫描或否定结果。

## 2. V22 已经推进到了哪里

### 2.1 原尺寸空间、周期约束和全侧作用已经真实执行

p6 表示六阶有限元基函数。MPC 是把周期边界上的从属自由度按实际复相位映射到独立自由度的约束；此次不只是预估了行数，而是建立了真实对象。[R2]、[R7]

| 项目 | V22 保存的实测结果 | 能说明什么 |
|---|---:|---|
| 原尺寸网格 | 30,464 cells，272×8×14 | 原始 50×25×140 nm 几何的资源/算子 pilot |
| p6 storage rows | 20,181,348 | 实际全局原生向量长度 |
| 独立 FE rows | 19,897,344 | 实际周期约束后的行数 |
| owned slave rows / coefficients | 284,004 / 284,004 | 全局 `topological_trace_p6` MPC 已 finalized |
| 边界面 | top 2,176；bottom 2,176 | 每个已执行模式均作用于本侧全部边界面 |
| 已完成模式 | 18,968 / 32,060，约 59.164% | top 16,030 全部；bottom 2,938，剩余 13,092 |
| 实际科学 checkpoint | 7,976,570 B | 保存 Bα 的非零行和值、已完成 D/H 值及精确前缀身份 |
| Bα exact-nonzero rows | 313,344 | 一次加权、前缀聚合后的 Bα 输出支撑；不等于逐模式结构支撑 |

全局 MPC coefficient SHA-256 为 `9312e5f0ad152e517ffc5b7050951fe33ea75f2066bd2e6e7a40639e70366411`。两份局部 packet 使用 identity MPC，只限定在它们各自的局部见证范围；不能用局部零 expansion rows 否认真实全局约束。

18,968×2,176 = **41,274,368 个 mode–facet 逻辑覆盖对**。类积分和相邻同波矢 s/p 已有复用，因此该乘积不是独立积分调用数或实际访存次数。也不能再把本次总耗时乘 4,352 或 54 来推算全边界成本。

### 2.2 接口修复应该被接受，数值资格应该按实际范围报告

| 项目 | 审阅结果 |
|---|---|
| generated native residual | V21 的空 Bi/Di 维数问题已修：generated B/D callback 进入内部 residual 与修正路径 |
| raw trace MPC 语义 | generated B 使用局部 expansion 的共轭转置归并，D 使用 expansion 展开；已完成的 global direct 项不应再次做 MPC |
| generated factory / bounded contributions | 已有生产工厂及 B/D tile callback 要求，局部 V17 consumer 实际消费了 C_hat、−D_hat、Hhat |
| 独立原生 B/D 见证 | 每侧一个 882-row、degree-60 hash-bound packet；B/D 相对误差约 2.229×10⁻¹²，满足该 packet 的 10⁻¹⁰ 门 |
| 全侧装配一致性 | top 首模式、bottom 首模式的 B/D 支撑差为 0；误差约 10⁻¹⁶–10⁻¹⁵；使用共享积分 kernel，资格是装配路径一致性 |
| 真实 q 映射 | 尚未使用；当前 q witness 是两个局部单元的 2-column trace/port selector，四个 2×2 子块 |
| 旧 top forward 负结果 | 1.488391772882517×10⁻¹¹ > 10⁻¹¹，未被本轮覆盖；same-LU≤3 修正仍 NOT_RUN |
| 完整求解 | q 完整矩阵 0/8；factor、KSP、完整场、PDE、R/T/A 均 NOT_RUN |

上述修复可在 `p6_cell_condensed_action.py` 的 2411–2438、2558–2592、2780–2816 行核对。局部 selector 位于 probe 的 2360–2425 行。不能继续把已经修好的 generated residual/MPC 列为未实现，也不能将局部 selector 通过提升成原尺寸参考逆已接通。[R7]、[R8]

V22 正式冻结源码对应的定向回执为 **3 passed in 0.78 s**，覆盖 checkpoint 失败门、实际 component/MPC 两级筛选和终端覆盖重算；py_compile、diff check 通过。Ruff unavailable、完整 pytest/MPI4/CI、新 PDE、LU 修正及三个 MUMPS lifecycle fixtures 均未运行。主控公共 API 的 18 项通过仅说明 partial receipt 的语义符合合同。[R4]、[R5]

## 3. 先回答真实内部支撑：这可能直接消除最大的条件缓存项

### 3.1 当前最值得验证的假说

313,344 恰好等于两侧周期边界切向 face/edge 自由度计数：

```math
2\left(60\cdot272\cdot8+6\cdot2\cdot272\cdot8\right)=313344.
```

这是**结构线索，不是零内部耦合的证明**。当前数值是一个随机 Bα 的模式前缀聚合；模式间可能抵消，它没有给出 D，也没有覆盖 bottom 尾部。不得由此直接令 Bi/Di=0，不得只保留这 313,344 行作为新 kernel 的候选域。

但这一线索指出了一个便宜且有实际价值的实验：在每个 production functional 已完成真实 MPC 与两级筛选后、加入 Bα 聚合前，分别统计其 B、D 到底命中了单元内部还是独立 trace 行。现有 descriptor 已从 Basix 取得每 cell 的 **450 interior / 432 trace** 分区；现有 factory 明确规定 interior carrier rows 进入 Bi/Di，独立 trace rows 进入 direct 项。[R7]、[R8]

### 3.2 一次模式流同时产出所需库存

以实际 cell dofmap 建立一次紧凑的 interior-global-row → cell 映射，使用 sorted 数组或准入后的整数表；不建立无界 Python 嵌套字典。用真实约束身份核验 interior、独立 trace、slave/unknown 分类，禁止未知行静默掉落。进一步用实际端口 facet/edge 的实体 DoF 和 MPC 建立切向面集合，把 trace 分成“实际端口面”和“同 cell 其他 trace”，便于定位异常；该集合先用于观测，不能提前裁掉完整 882-row 候选。也可低成本比较旧 checkpoint 的 Bα 行集合与它是否相同，但这一前缀聚合检查仍不替代逐模式 B/D 证书。每个 mode：

1. 分别读取最终 `coupling_rows/values` 与 `projection_rows/values`。
2. 对命中的 interior cells 分别去重，计 `m_c_B`、`m_c_D`；对二者并集每 cell 只计一次，得到 `m_c_union`。
3. 分列 B/D 的 interior 条目数、最大绝对值、direct trace 条目数、所涉 side/class/mode 以及 support digest。
4. 持久保存紧凑 cell 计数和模式范围，在完成全 32,060 modes 后计算 histogram、max、非零 cell 数、Σm_c、Σm_c²。
5. raw 882-row tiny 值、第一次筛选和最终 production 支撑分别记；这里指在线统计/digest 与有限见证，不保存全 mode×facet×882 数值。不改两级 10⁻¹³ 相对阈值、不加绝对 floor、不提前删 tiny。

```math
m_c=\#\{j:\;B_j\ {\rm or}\ D_j\ {\rm has\ retained\ interior\ support\ in\ cell}\ c\}.
```

**不需要先建立完整 global carrier 才能测这些量。** 旧 checkpoint 只存聚合 Bα 与 D/H 值，不能恢复已完成前缀的逐模式 cell 支撑；这决定了仅续跑 13,092 个模式还不能得到完整库存。

### 3.3 按实测结果选择表示，避免继续背负不存在的缓存

| 全模式生产支撑结果 | 必须采取的动作 |
|---|---|
| B、D 的 interior 支撑全部为空 | 给出配置绑定、全模式覆盖的零证书；内部 Bi/Di、XiB 及其局部端口修正按实际为空表示；全局边界 B/D 继续有界生成 |
| 只有少量 cell/mode 命中 | 按实测 m_c 和左右独立支撑保存/生成，重算 unique backing、派生缓存和峰值 |
| 大范围命中 | 保留既定 generated/bounded tile 路线，以实测 Σm、Σm² 和生成成本设计容量；不回到全量 dense cache |

在同一生产方程、同一 MPC 行语义下，若全模式确证 Bi=Di=0，则以下简化是原方程的直接结果：

```math
\widehat C=B_t,\qquad
\widehat D=D_t,\qquad
\widehat H=H_p.
```

零证书仅约束本次 target 的边界几何、dofmap/MPC、完整 mode/e/traction/Hp/gauge 和两级筛选身份。只有这些实际 port descriptor 相等且有 hash/显式变换证明，才可复用到 filled-reference 的对应实例；否则 reference 及各 twist/sector 的生产端口需独立统计。不能仅因两者几何尺寸相同，或分别记录了 physical-model hash，就删除 reference 的内部缓存。

原体积凝聚、direct trace B/D、原始对角 H_p、RHS/恢复和真实 q 映射仍然存在。这不是把原生积分中的 tiny 擅自改零，而是使用**现有生产筛选输出**的实测支撑。不能反过来用 unfiltered 局部 packet 的 tiny Bi/Di 重新定义一个与生产路径略有不同的算子。

Review V22 的 **2,471,268,925,440 B** 是“全部 4,352 个边界 cell 均关联本侧 16,030 modes”时，Bi/Di、XiB、Bhat/Dhat 若全部缓存的条件情景。它不是实测 RAM，更不是 2 TB 不可能的下界。V23 必须用真实支撑替换这一假设；若证实对应内部支撑为空，就删除这些条件项。direct trace 载荷、体积局部数据、q/因子、向量和系统余量仍另计。[R13]

### 3.4 direct-only 仍需真正有界的生产接口

**即使内部支撑全部为空，现有 direct trace 路径仍会全量缓存，必须补齐这一段。** generated 工厂在 2801–2802 行要求非空 cell mapping，构造器在 644–649 行也挡住没有 cell generator 的 research+streamed 情况；不能只改工厂，不能造一个假 cell/假非零项绕过。

当前构造器把 direct terms 全 tuple 化，`_prepare_direct_terms` 保留每 mode 的 original/active 两套 B/D rows/values；owned 快速分支仍另外分配 active 版本。现有 carrier builder 也会把整个 iterator 消费为 tuple，之后分 batch 作用仍属于全量缓存。[R8]、[R9]

作为另一个条件情景：若每个 mode 的 B、D 都保留本侧全部 156,672 个切向行，**仅 complex128 values** 为 160,732,938,240 B；尚未计 indices、original/active 副本和构造重叠。这不是当前实测库存，但足以说明“内部零耦合”不会自动让旧 direct 缓存有界。

最小实现是在现有生产模式流上增加 global direct provider，使 metadata/身份可以常驻，数值仅保留有限 mode/row tile。复用 `iter_fullspace_dtn_functionals_from_surface`，避免全量 tuple 或按全部模式保留数值的 dict；连通 `_add_direct_reduced`、`apply_B_full`、`apply_D_full` 和 contribution layouts/values。已经 MPC 归并的 global rows 只转换为 active 编号，不再次施加共轭 MPC。

允许合法的零 cell-generator 情况，并保持原 H_p 作用与恢复/RHS 语义；若存在少量真实内部支撑，同一 provider 只负责 direct 部分，内部项按实际独立处理。对照覆盖非零 trace/port RHS、两个以上模式的释放/借用生命周期，以及适用的 native residual 项；不要求先建完整 target 凝聚系统才能验证有界 direct 接口。

支持联合 Bα/Dx 或有限多 RHS 可减少重复 sweep，必须记录实际重复生成次数和工作区。仅把接口名字改成 streamed、或把全量 carrier 藏到 provider 闭包里，不算完成。

## 4. 把重复全域扫描缩到真实边界候选域

### 4.1 已定位的热点与已有复用

probe 的 `assemble_component` 第 1029 行创建全体 20,181,348 行的 complex128 零向量；第 1062–1067 行又对它做 abs、max、count_nonzero、筛选。**每次 component 调用**，仅该向量为 322,901,568 B，magnitudes 为 161,450,784 B，尚未计后续扫描与临时对象。[R7]

当前代码已按 `(side,class,permutation)` 复用积分、向量化 facet 原点相位，并在 fullspace iterator 中复用相邻同波矢 s/p。必须保留这些优化。全扫描的逻辑向量构造量应按**实际 component 调用数**乘上述字节计算，不能直接按 32,060×2 次强算，也不能将逻辑数组体积称为实测 DRAM 流量。[R9]

### 4.2 保持数学和浮点顺序的最小改法

预计算每侧候选集合 S：

- 所有真实边界相邻 cell 的完整 882-row `cell_dofs` 并集；
- 加入这些行所需的 finalized MPC master closure；
- 含 raw interior/trace 和 slave；只有结构上确定不受装配与 MPC 路由影响的域外行可以省略。

在 S 上建立 global→compact 映射和可复用 accumulator，最后仍输出原始 global row IDs。保持原 group/facet/local-row 散射顺序、相位公式及精确零判断；先复制所有相关 slave 值，再按原 master/coefficient 顺序执行共轭归并，最后清 slave。该顺序关系到浮点抵消及阈值边缘的保留行。

第一层筛选仍在完整候选域求全局最大值，并使用严格 `abs(value) > 1e-13 * maximum`；域外结构零不改变最大值。第二层直接复用 `_combine_owned_entries` 的 component 权重、stable mergesort、reduceat 和全局阈值。不能在每个 facet、class 或 row tile 内单独设最大值。[R7]、[R9]、[R10]

Bα accumulator 与 checkpoint 也使用结构候选域；需要原生全 FE 向量时在末端经过准入后一次 scatter。Dx 所需 field 值可以在真实 MPC backsubstitution 后一次 gather。不要把局部 batch 擅自扩成多份全 FE 向量。

### 4.3 先同模式对照，再执行一遍有新增交付的全扫描

有限对照覆盖两侧首/中/尾波矢、相邻 s/p、非平凡周期行、强抵消或接近筛选边缘的模式。旧/新路径使用同一场和 α，顺序执行并记录生命周期；核对两层 cutoff、精确 support 对称差=0、排序、B/D 值及 Bα/Dx。只重编号且运算顺序不变时优先要求数值字节一致；若出现变化，定位原因和影响，不能仅以一个小相对误差掩盖 mask 改变。

独立 degree-60 packet 用于检查原生积分数值，旧/新同 kernel 对照用于检查表示和装配；两者分开。以实际边界类/方向和波矢范围扩展有界独立资格，优先尚无见证的原尺寸 class/permutation 与高波矢/近 cutoff 代表。现有 54 个边界 class 被扫过，不等于全 60 类体积/方向资格；不要要求每个 mode×facet 重做独立高阶积分才允许有效的表示测试。

**默认安排一遍优化后全模式扫描，同时产出 Bα/Dx、逐 cell 库存和性能分项。** 这是获得旧 payload 中不存在的库存，并验证新表示的必要工作；不先机械重放旧慢路径，不先消耗大半窗口做通用恢复框架，不另做两遍分别只测 action 和库存。若新实现尚未等价，则保持旧路径做受影响范围的定位或有界库存段，独立 q-map/回执工作继续。

## 5. 从局部 selector 推进到真实 q 映射下的矩阵块

### 5.1 下一步应该建立什么

真实 q/sector 映射说明全局自由度如何按参考预条件器的周期相位组合。V22 用两个任意 trace/port selector 验证了 contribution API；V23 要使该 API 消费**原尺寸 filled-reference 预条件器的真实八 q 映射**。目标非可分算子与参考算子的物理身份分别记录。[R7]、[R8]、[R11]

选择有明确行列范围、当前内存可容纳的一个或数个 q0/sector tile，至少涉及非平凡周期轨道及真实端口。对选定块包含其所需的全部原尺寸前驱 cell/facet/mode 贡献；不得只取两个 packet 却使用全局标签。

```math
T_{qr,IJ}=R_I P_q^{H}K_{\rm cond}P_rR_J^{T}.
```

这里 P_q 从实际 sector 坐标映射到已经 MPC 凝聚的 active trace + 全部 ports，shape 和复系数须绑定实际 descriptor；R_I、R_J 只选取要测的真实行列。该坐标层不重复施加 E 或其共轭转置。需要覆盖的凝聚项包括体积 Schur、C_hat、−D_hat、Hhat 和 direct trace；已经全局 MPC 归并的 direct 项只加入一次。若分析目标在 q 基下的块，实际出现的 q≠r 耦合必须保留，不套用参考问题的对角化结论。

数值对照使用同一实际 tile 的独立逐项投影：直接读取冻结的 production B/D/Hp 和所需真实局部体积/LU 数据，不让同一个 generated iterator 同时制造候选和参考。逐类报告 C、−D、H 及体积项的误差、非零和支持，沿已冻结的 10⁻¹¹ 级对应门验证，不能用大体积块的范数淹没遗漏的小端口项；参考零块单独按原适用绝对门和确切零范围处理。

### 5.2 按依赖连续推进，不等整套 q 才测一个块

| 情况 | 应继续的工作 |
|---|---|
| 真实 q map 与 direct 端口项已具备，相关体积类资格未齐 | 完成真实端口 tile、映射身份、支撑、nnz、字节和时间；完整 K_cond tile 标为部分完成 |
| 选定 tile 所需局部逆/体积数据已资格化且资源可容纳 | 完成该真实凝聚 tile 对照，计入 native/temporary workspace 与生命周期 |
| q0 tile 成本已测，但完整 q CSR/因子尚无上界 | 给出下一阶段基于实测的 build/symbolic/numeric 准入判断；本轮不直接分配全部 q 或启动 factor |
| top known-forward 仍超限 | 该 known-forward 链路的通过资格保持未关闭；不能据此断言 Vii 的 LU 本身错误。同一真实数据的诊断 tile 仍可测并分列结果，边界 B/D、库存、映射和端口 tile 继续 |

本轮结果应叫“真实 q 映射下的有界 tile 已测”，并列出 q/r、行列、覆盖项、遗漏项、tile nnz 和对象实际字节。**完整 q 矩阵计数仍是 0/8**，除非确有对应完整矩阵证据。不得用两个局部 selector 的通过替代这个交付。

当前普通 target worker 仍在 5387–5395 行走 `from_carrier(..., port_coupling_mode="cached")`；probe 的局部 generated 通过不等于完整 worker 或 cached reference 已完成替换。V23 应给生产调用入口实际消费 bounded/direct provider 的证据，至少贯通本节真实 tile 所走的链；未连接部分继续明确计入后续预算。[R11]

## 6. 普通 bug 集中修复，主线按真实依赖前进

| 已核对的问题 | 最小处理 | 不应触发的工作 |
|---|---|---|
| E2 专用只读 CLI 对 V22 root 报缺 candidate-summary | 使用已有 `task40_v20_service_workflow.py check-partial`，按正式 manifest 提供 input/summary/manifest/numerical-output/stop-stage；保存一次 CLI/API 一致性回执 | 不新写一套 checker，不重跑旧 FE/PDE |
| checker q keys 写死 0–3 | 从 hash-bound profile 得到 q_count；用 E2=4、target=8 的实际 producer 结构测试完整、缺项和非法项 | 不改成固定 8 来破坏 E2 |
| one-q inventory 层级不一致 | worker 目前放 `physical_rhs_stage`，wrapper 读顶层；统一或按版本显式解析 | 不把已有字段报成 UNKNOWN，也不猜造 q 内容 hash |
| worker cleanup 与 wrapper 层级/含义不一致 | native owner、temporary、factor 和外部 descendants 分层绑定；退出作用域后再采样实际释放 | 不用 watchdog 的退出证明补写旧 worker 原字段 |
| V22 window path 在 probe 内硬编码 | 新包显式传入/注册 V23 manifest path/hash/scope，service/probe/watchdog/账本读取同一身份 | 不改旧 V22 日期、不删 window 校验、不仅改一个 heavy flag |
| response/index 与预算快照标签滞后 | 最终编辑后重算内容 hash，快照附 as-of/sequence/scope | 不追写旧 numerical source 或旧失败字段 |
| generated/cached 混合分支的承诺超出实现 | 当前 Hhat/contribution 对混合 cached cell 可能漏项或拒绝；最小先明确拒绝该混合配置，或补完整对应 tile 分支 | 当前 V22 全 generated 见证不受影响，不为此重做小 PDE |
| 旧 top forward 与 MUMPS lifecycle 未关闭 | 原有 same-LU≤3 有界修正；initial symbolic、post-eviction next-q、numeric cache-miss 三个真实生命周期 fixture | 不默认再跑 E2 或新小 PDE，不放宽局部 forward 门 |

位置证据：checker 544–545 和 823–835 行；stage runner 946、965 行；worker 5830、5874 行；service 1274–1298、1463–1476 行；probe 1228–1242 行。混合分支见 p6 构造器 742–746、contribution 1793–1794、1985–2003 行；当前全 generated 见证不触发该缺口。[R7]、[R8]、[R11]、[R12]、[R16]、[R17]

这些是有界实现和定向验证任务。不要在第一项 import/shape/schema/path 错误处提交“等待下一轮审阅”然后停止；保留失败，修正明确原因，运行最小相关测试后继续。在一条数值路径不合格时，只停止依赖它的部分。真实输入/ABI/材料/网格/MPC 身份错误、数值不等价、内存或时间门触发仍必须受控停止相应阶段。

## 7. 用完整生命周期回答 2 TB 与 48 h

### 7.1 当前资源结果的范围

| 量 | V22 记录 | 解释 |
|---|---:|---|
| process-tree RSS peak | 3,242,729,472 B | 本次全局 FE/MPC 与部分 B/D probe 的进程树峰值 |
| dedicated cgroup peak / cap | 3,533,070,336 / 17,179,869,184 B | 16 GiB 专用上限下的实际记录；与 RSS 口径不同 |
| task swap / OOM-kill | 0 / 0 | 本次任务未借助 swap，没有 OOM-kill |
| PSS | null / disabled | 不补造 PSS |
| run monotonic | 3,991.941 s | 含准备、校准、扫描、checkpoint 的运行区间 |
| conservative attempt | 4,383.978 s | 对应保守时钟口径，不是纯 kernel 时间 |
| 外部清场 | descendants_cleared=true | worker native/temp 原字段仍 UNKNOWN |

这说明原尺寸准备和全边界作用开发已经可以在本机继续。它不证明完整最终场只需约 3 GB；完整 q、因子、全部局部恢复数据、Krylov、输出和检查器尚未同时出现。[R2]、[R4]

最终目标固定为整机物理 RAM **2,000,000,000,000 B**，任务 swap=0。应核算同时存活对象及系统余量：

```math
\max_t\left[
M_{\rm FE/MPC}+M_{\rm volume/ports}
+M_{\rm q/conversion/factors}+M_{\rm vectors/output/runtime}
\right](t)+M_{\rm OS/other\ reserve}
\le 2\times10^{12}\ {\rm B}.
```

V23 沿用当前本机 16 GiB 硬上限、动态 cap、host reserve、专用 cgroup 和零任务 swap，逐阶段准入；不由旧 3.53 GB 推断所有新对象均可容纳。≤8 GiB 可作为优化工作集目标，不能无实测宣称达到，也不另设为阻断独立进展的硬门。地图、候选行、整数索引、原生积分缓存、component、B accumulator、D/H、reference/checker 和同时存活临时对象均计入。

### 7.2 目前约两小时的只是一次粗扫描量级

按已完成模式数对同一原尺寸实例做比例规划，完整 B/D 扫描约为 **6,747 s / 7,410 s，即 1.87 h / 2.06 h**；旧 suffix 对应约 2,755 s / 3,026 s。二者分别使用 monotonic 与保守 attempt，**是推算，不是稳态一次 matvec 实测，也不是完成时间上界**。固定准备/校准、top/bottom 的 26/28 类差异、checkpoint 均影响该外推。

已有 raw receipt 中若保存了校准时段，可只读提取镜像到 compact，无须重跑。新实现至少以 exclusive timing 分解：FE/MPC/descriptor、独立校验、类积分/cache、phase/scatter/MPC、mask/组合/sort/hash、Bα/Dx、checkpoint/采样；嵌套子项和父区间不重复求和。记录实际 component 调用、cache 命中及不同场/α下的代表性后续作用成本，不把某一字段 `last_component_seconds` 当整段计时。[R7]、[R9]

对最终单场，必要 prepare/JIT/build、迭代及真实检查、恢复/输出和 checker 都在 172,800 s 内。按互不重叠的成本可写为：

```math
T_{\rm field}
=T_{\rm fixed}
+N_{\rm port\ passes}\,t_{\rm port}
+N_{\rm numeric\ misses}\,t_{\rm numeric}
+T_{\rm other\ volume/PC/Krylov/recovery/check}
\le172800\ {\rm s}.
```

若用总 PC 实测时间，已包含的端口生成或 numeric miss 不再重复相加。当前 one-q refactor 用较少同时驻留因子控制峰值，但可能在每次 PC 中付出重复 numeric 成本；外层步数少不能代替总时间账。下一步必须取得真实目标的重复端口成本、参考 q/因子成本和迭代增长证据，才能推导 48 h 允许的迭代数或生成次数。

### 7.3 checkpoint 必须可用，也不能吞掉吞吐

现有 checkpoint 是有用的科学数据，但 probe 从零创建 RNG、Bα、D/H 和 digest，iterator 没传 `start_index`；因此“保存了 checkpoint”不等于已经可以续算。[R7]、[R9]

V23 优先完成紧凑扫描及库存，让新扫描本身支持精确分段恢复。至少保存：payload hash、source/数值 recipe、实际输入与物理身份、mesh/dofmap/MPC、mode/gauge、field/α 身份、RNG 状态、next index、B/D/H、cell/support 计数和累计分项。所有数组、计数和范围由 reader 校验。

确需复用 V22 前缀时，可以核验相同运行算法并重放廉价 RNG 抽样到对应位置；不能换一个 seed 或跳过场生成的 RNG 消耗。旧 SHA hexdigest 不能作为 hashlib 内部状态恢复，应保存“旧前缀摘要 + 新分段摘要”的明确清单，不能假称是单次连续扫描的总 digest。只有经过证明兼容的数值片段才能合并；缺失的逐模式库存不能从旧 Bα 反推。

每 8 modes 的原 checkpoint 还会全域 flatnonzero、写盘、校验和 fsync。改用 compact accumulator，按实测时间或有界进度段触发原子双槽 checkpoint，并在 graceful stop 前强制 flush；checkpoint 间隔和最大可能丢失进度写进运行记录。保留持久化，不靠取消证据换速度。

## 8. V23 独立 6 h 工作包与交付顺序

### 8.1 旧窗口已经结束，本包范围与时钟明确登记

旧 V22 manifest SHA-256 为 `a4da3d83c2a06672a2337a518dcc8a8bb5d12a446e995783e0f9dd406427d777`；T0 `2026-10-10T02:34:32Z`，数值截止 `08:24:32Z`，deadline `08:34:32Z`。本次用户在其结束后请求进一步推进。本 review 声明一个**范围明确的新 V23 工作包**，不恢复旧包余额或把旧失败改名重新计时。[R1]、[R4]、[R6]

旧 watchdog cumulative 20,889.287384595274 s、probe 20,887.459420917243 s 分属不同读数；约 1.828 s 差额保持未分配。主控提交前 seq=16088 cumulative 21,574.978431403273 s 是较晚快照，仍不含其后全部提交/推送费用。index 的 watchdog_end 应标历史 as-of，不能当现时余额。

| V23 项目 | 合同 |
|---|---|
| scope | 紧凑边界作用、全模式支撑与成本、真实参考 q-map 有界 tile，附属修复按第 6 节 |
| manifest 建议 | `benchmarks/artifacts/task40extra_0p7nm_engineering/local_v23_wsl/campaign_window_v23.json` |
| T0 | 主控收到本 review 后开始本包第一项实际工作时一次冻结；实现/测试计入，不能等数值运行才开钟 |
| 总窗口 | T0 + 21,600 s |
| 收口预留 | 1,200 s；本次数值工作最晚于 T0 + 20,400 s 停止，提交/回读也在总窗口内安排 |
| 扣账 | UTC、monotonic、boot/namespace 与保守累计分别记录；等待、修复、测试、运行、收口计入 |
| 资源 | 同一时刻一个 heavy case，既有本机 cap/ABI/输入/零swap 门 |
| 到期 | 保存真实前缀和未完成项、清场、收口；不因重启或普通 bug 刷新 T0 |

### 8.2 连续推进的优先级

1. **先打通最短可运行路径。** 核对 source/artifact/ABI、正确 stage/window/check-partial 接线；加入紧凑映射与在线支撑计数，做最小相关测试和同模式旧/新对照。只读提取现有 phase 字段。
2. **尽早进入原尺寸优化扫描。** 根据两侧新实测 block 成本和剩余窗口作有余量的计划；除 1,200 s 收口外，为已声明的真实 q-map/tile 工作预留可执行时段（建议 45–60 min 作为计划额，非数学硬门）。一次同时产出全模式 action、内部/direct 库存和成本；若全扫描不能同时留出后续工作时间，按有用批次持久化，同时推进独立 q-map/端口 tile，不盲启整扫再耗尽整包。不要把全部窗口花在通用恢复、日志框架或无关重构上。
3. **由实测支撑马上选择生产表示。** 取得全模式零内部证书则走合法 direct-only；否则仅为实测内部支撑保留生成式局部项。完成第 3.4 节 global direct provider 的真实入口与生命周期验证，两条路线都保持边界直接项有界。provider 和真实 q-map 的接口/有限片段开发可与库存扫描按依赖交错推进，无须等全模式计数才开始写代码。
4. **推进真实 q-map tile。** 所需映射和端口工作不等待 full q/完整场；局部体积/逆相关数值块按其资格推进。预算不足时交付真实覆盖子集、其余成本投影，不改写为全 q 完成。
5. **旁路关闭有限断点并收口。** 同 LU 修正、三个 lifecycle fixtures、producer/checker/cleanup 形状集中处理；对应失败只阻止依赖部分。最终刷新索引一次，主控核对提交与证据后结束。

本轮不启动原尺寸全 q CSR、symbolic/numeric、KSP 或完整 PDE，也不迁移到工作站；这些阶段将在真实支撑、q tile 与容量成本支持下进入下一阶段准入。当前工作必须产生原尺寸数值/资源结果，不能以“尚未允许完整 PDE”为由只交文档。

沿用 canonical worktree `/home/shenjh/Projects/MyFEniCSx_task40extra_0p7nm_engineering` 与同一分支；执行者负责实现、测试、运行和证据，不 commit/push；既有主控审查、冻结源码、集中提交/推送。保持当前聊天与工作目录，不新建 Codex 聊天/checkout/worktree，不 SSH，不切主机/项目，不改 master，不使用执行侧 collaboration subagents 或自动化。[R14]

正式 attempt 绑定冻结 source，不热改运行中代码。普通 bug 在当前 scope 内局部修复，新增 attempt 保留旧失败，仅对真正受影响路径复验；不逐个 bug 要求下一次 review。

### 8.3 Response V23 必须首先回答的结果

| 必答问题 | 最低可核验交付 |
|---|---|
| 原尺寸完整 B/D 到哪一步 | exact modes/side/range、全侧 facets、Bα/Dx/H payload 与 hash；complete 或真实 partial |
| 内部耦合到底有无 | B/D 分开统计、m_c histogram/Σm/Σm²、direct 库存、零证书或实际非零最坏见证；未扫范围单列 |
| 优化是否有效 | 同模式旧/新支撑与数值对照；每侧分项/重复成本、实际 component/cache 次数、工作集/峰值；实测 speedup 不预填 |
| 真正省掉了什么 | unique backing、alias、同时存活峰值；更新旧条件情景，列清 direct/reference/q/factor 仍存成本 |
| 真实 q tile 做到什么 | 实际 profile/map/hash、q/r/I/J、贡献覆盖、逐块数值、nnz/bytes/time；完整 q 计数不混淆 |
| 下一阶段是否可准入 | 剩余数值资格、完整 q build/symbolic/numeric 的已知成本与未知项，具体下一工作，不以空泛 NOT_QUALIFIED 收口 |

提交 `response_v23.md`、outcomes summary/test summary/run index 及必要紧凑的 operator/support/performance/q-tile 回执，可合并 schema，避免空文件堆积。大型数组与日志留 ignored artifact，只提交身份、hash、命令和统计。正式新资源运行/受控停止同步模型总账及项目回顾。

定向测试应覆盖真实改变：紧凑/MPC/两级筛选、生产形状的支撑归属、checkpoint 中断恢复、direct-only（若启用）、实际 q tile consumer 和 receipt。沿用未受影响的昂贵证据；报告 full pytest/MPI/CI 等真实未运行项，不因文档修正反复跑 PDE。主控最终给完整 HEAD、base、工作树状态、文件清单、结果 hash 索引与时钟快照。

## 9. 小模型何时结束，何时能算最终大模型

**小模型已经完成了允许向原尺寸阶段推进的最低职责。** 它用于验证同一 0.7 nm 材料/边界/方程、凝聚恢复、原方程残差和基本预条件行为；不能要求它再降若干迭代步数，才允许建立原尺寸算子。V22 本身已经迈出了原尺寸空间和全边界作用这一步。[R13]

当前预条件器是否有用，要看同一真实问题的**总峰值内存 + setup/每次 PC/重复分解总时间 + 最终原方程残差**。迭代次数低只有与这些指标一起才有意义。V23 的重点是让已经选定的方法以有界存储和足够吞吐被完整执行。

进入首次原尺寸完整求解前，需使原尺寸算子/RHS/恢复链、reference 逆、真实 q/因子及工作区成本可准入，并具备适用的局部数值资格和受控停止机制。**完整 A6 通过是求解后的成功门，不能要求先有一场成功原尺寸解才允许第一场原尺寸解。**

达到最终目标还需：原 50×25×140 nm、0.7 nm、complex128、完整非可分几何与模式合同下，完整场及原 A6 门、官方 R/T/A/体吸收与复 E/H 输出通过；整机预算≤2 TB、任务 swap=0、必要全流程≤48 h；并取得任务要求的网格/阶次/模式精度证据。当前 Ny8/Nz14 是原尺寸资源与算子 pilot，尚不能因解出该离散就宣称最终精度已合格。

## 附录 A. 远程文件内容复核

| 文件 | 本次 UTF-8 内容 SHA-256 | 对照结果 |
|---|---|---|
| response_v22.md | `ded69e2f44c31ca2e4c82b00cfd66b708a862accf29f2206f0552e9785f5d5b5` | index 为较早值；两次远程回读一致 |
| target_operator_probe_v22.json | `0491ef3430247f405a6744a9bc69aa7200833910e660c4e682464c724e04738a` | MATCH |
| target_port_inventory_v22.json | `c22cd3e6ed22d64ce0de6fb07df14e5e1b06c6c6acf39a042d04e10b75389fb4` | MATCH |
| targeted_tests_v22.json | `09dcbc68a92965c82892261541bc8ee5bb3718dac9be29a7c8c1c20173f782dc` | MATCH |
| scripts/task40_v21_readonly_recheck.py | `f21ec5d6a559d7febccf0729cefc1b0f659284c08c80356a337dc27fe8652866` | MATCH controller receipt |

原始 receipt SHA-256 `0385bce9c595358d08eaa3c4903a7fc4be647ecb51bf73ad506429f7237d38d5`、checkpoint JSON SHA-256 `aae2e73f5254b9c037a702427f0620b52b8f64895b2eaefd76431994338adb13`、stream prefix SHA-256 `617cb54178e46928647b245f5f5de1225dc4ac614a009e0735746b86cfcfbe54` 来自 V22 已提交回执，作为后续本机读取的核对入口；本次未冒称远程重新计算了这些 ignored 原始文件的 hash。

## 附录 B. 冻结证据与源码入口

以下链接全部固定到本次审阅的结果 HEAD，后续分支更新不改变本报告的证据身份。

| 编号 | 文件 / 用途 |
|---|---|
| [R1][R1] | Response V22：运行、边界和窗口说明 |
| [R2][R2] | V22 operator compact：FE/MPC、前缀、数值和资源 |
| [R3][R3] | V22 port inventory：边界/模式/类覆盖与未知库存 |
| [R4][R4] | controller readback：payload、公共 API、预算快照 |
| [R5][R5] | targeted tests V22 与未运行范围 |
| [R6][R6] | run index：证据索引、运行及历史快照 |
| [R7][R7] | 原尺寸 probe：FE/MPC、全侧装配、checkpoint、局部 selector |
| [R8][R8] | p6 cell condensed action：内部/direct 归属、generated 与 contribution API |
| [R9][R9] | fullspace DtN：完整生产模式流、s/p 复用、start/stop index |
| [R10][R10] | DtN 两级 production 相对筛选与组合 |
| [R11][R11] | Task40 worker：cached 路径、one-q 实际生产输出 |
| [R12][R12] | service 的 check-partial 入口与正式服务流程 |
| [R13][R13] | Review V22：既定路线、条件库存与小模型退出/最终目标 |
| [R14][R14] | Task40 本机执行与主控分工 |
| [R15][R15] | 原尺寸 Ny8 V22 tracked 输入模板 |
| [R16][R16] | stage runner 的 q inventory 与 cleanup 消费层级 |
| [R17][R17] | readonly checker 的 q keys、公共 API 与旧 E2 CLI |

本报告仅新增同分支 review。交付核验包括 Markdown 表格/公式、固定来源、提交后精确内容回读及 GitHub rendered view；实际提交 SHA、报告内容 hash 和渲染核验结果随本轮最终回执给出，不预写尚未发生的核验通过。

[R1]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/docs/task40extra_0p7nm_engineering/response_v22.md
[R2]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/docs/task40extra_0p7nm_engineering/outcomes/records/target_operator_probe_v22.json
[R3]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/docs/task40extra_0p7nm_engineering/outcomes/records/target_port_inventory_v22.json
[R4]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/docs/task40extra_0p7nm_engineering/outcomes/records/controller_readback_v22.json
[R5]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/docs/task40extra_0p7nm_engineering/outcomes/records/targeted_tests_v22.json
[R6]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/docs/task40extra_0p7nm_engineering/outcomes/records/run_index.json
[R7]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/src/solvers/task40_v22_operator_probe.py
[R8]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/src/solvers/p6_cell_condensed_action.py
[R9]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/src/solvers/fullspace_dtn_action.py
[R10]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/src/solvers/dtn_port_3d.py
[R11]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/src/runners/task40_v10_worker.py
[R12]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/scripts/task40_v20_service_workflow.py
[R13]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/docs/task40extra_0p7nm_engineering/review_report_v22.md
[R14]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/docs/task40extra_0p7nm_engineering/AGENTS.md
[R15]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/input/task40extra_0p7nm_engineering/target_original_ny8_operator_probe_v22.dat
[R16]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/src/runners/task40_v20_stage_runner.py
[R17]: https://github.com/Rookie1234567/MyFEniCS/blob/084270e06f7a2c4d4e540ed839c7584d82fe32af/scripts/task40_v21_readonly_recheck.py
