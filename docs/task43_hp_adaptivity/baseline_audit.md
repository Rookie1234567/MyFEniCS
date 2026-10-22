# Task43 基线审计与历史资产选择

审计日期：2026-10-22。仓库：`Rookie1234567/MyFEniCS`。

本文记录创建 Task43 时的远程快照、可复用能力和已知失败，供任务书与执行回执引用。
本文中的历史结果来自固定提交的源码、review、response 与 outcomes；Task43 本身尚未运行 PDE。

| 项目 | 冻结决定 |
|---|---|
| 新分支 | `task43_hp_adaptivity` |
| 创建来源 | `task40para_phi90_mesh_modes_direct` |
| 基线 commit | `405e3aff42ac421a4c99315df1ed9b96941ecbe4` |
| 基线 tree | `87b08dc47047c8ae3537428b8419e402d71d60e9` |
| 首个科学对象 | 新 `phi90 / p50×50 / g17×20` 几何、原尺寸、13.5 nm |
| 任务起点 | 明确资格化 p3；180 cells（3×10×6）只是起始候选，必须核对几何分面与材料标签 |
| 初期求解路线 | 小规模 direct 校准真实 h/p 闭环，随后独立资格化迭代接线 |
| 本次授权 | 用户已明确授权 ChatGPT 创建新分支；这是本次任务例外，不修改仓库一般角色原则 |

## 1. 主线与基线选择

### 1.1 当前有两条用途不同的主线

| 分支及固定提交 | 当前职责 | 对 Task43 的用途 |
|---|---|---|
| [`task40para_phi90_mesh_modes_direct` @ `405e3aff`][base-commit] | 新 phi90 几何的 direct、网格与模式对照主线 | 新建分支的直接祖先；提供几何、材料、端口、完整输出和 direct 比较基础 |
| [`task41extra_phi90_p50x50_g17x20` @ `59722cca`][iter-commit] | 0.7 nm 的迭代与实际几何算子主线 | 保留为后续迭代接线参考；不整体合并到 Task43 |
| [`task40extra_dot_parallel_cloud` @ `a9b21d8a`][dot-tree] | 云端 hp/迭代探索及报告证据 | 借鉴动作验证、方向选择与恢复误差教训；不能视为完整可移植实现 |

这里的“主线”按用途区分。不能因为 Task41 编号更大，就把 Task40para 的新模型 direct 基础视为过时。
Task43 首先需要区分网格和阶次改变带来的场差与求解器误差，因此选 Task40para 可减少同时改变的求解器因素。
这项选择不否定 Task41 的迭代工作，也不把 Task40para 宣布为全仓唯一生产主线。

### 1.2 Task40para 的正面证据与边界

| 已有证据 | 审计解释 |
|---|---|
| Y5-1 `[6,14,6]`、504 cells，以及两个 Y6 576-cell 结果保存了完整输出 | 可以作为新模型 y 方向工程对照；具体身份见 [D15 保存输出比较][para-comparison] |
| 三组两两比较覆盖 612 channels、复振幅和同坐标 E/H；分别按通道 `1e-6`、总量 `1e-5`、复振幅/场 `1e-4` 的标准通过 | 支持停止继续加密 y 的当前工程决定；不等于所有方向、所有物理量已经收敛 |
| `[6,14,8]`、672-cell z 细化这一候选仅有静态计划 | 不得将该计划写成已运行、已通过或 Task43 可直接继承的数值结果 |
| 另有 2026-10-22 保存的 B/Z1/Z2 对照：`[6,4,6]`、`[6,4,8]`、`[6,4,10]` | Z1→Z2 的三个比较门通过，但其 R 约 0.585263，与 y 更丰富的 Y5 约 0.251355 差别巨大；其他方向欠分辨时，一个方向的稳定不能证明准确性，见 [B/Z1/Z2 记录][para-bz] |
| 记录仍保留 `FULL_DTN_NOT_VERIFIED` 与 canonical sidewall `NOT_MEASURED` | Task43 必须延续这些未验证边界，不以网格一致性替代 DtN 截断与侧壁审计 |

上述状态由 [Task40para outcomes][para-summary] 与固定记录共同支持；不能只取某一条总反射率相近来声称基线精确。

### 1.3 Task41 的最新状态不能由旧 summary 代替

| V9 进展 | 截至固定 HEAD 的事实 |
|---|---|
| 保存局部数组的 screen | 已实测 `LOCAL_CANDIDATE_READY`；不是“V9 尚未开始” |
| 全域 attempt `20261022T034957.536640Z` | 在 volume-only owner 前因 saved-source 路径读取问题失败；不是物理收敛反例 |
| 全域 attempt `20261022T041809.325937Z` | 在 prefix qualification 登记链路失败；本次逐键数值和审计计数未持久化，记为 UNKNOWN |
| 最新修复 | HEAD 补齐 evaluator 资格登记和定向 fixture；尚无 fresh full-action/recovery PASS |
| 当前资格 | 局部 READY 与接线修复不能授予 0.7 nm 完整解或 local hp 迭代资格 |

精确依据为 [V9 preparation 的后续运行与修复记录][iter-v9]，不是早先 review 中的准备阶段描述。
Task41 的 q-reference 利用规则参考及 y 平移结构；局部 h/p 会改变拓扑、实体阶次、约束和转移。
因此后续必须证明同一自适应离散上的算子、恢复与预条件器一致，不能仅复制 BAL_H 开关。

## 2. 停止两条 NN 当前研究线，同时保存证据

### 2.1 停止决定的范围

建议结束用户所称 `task42-NN` 与 `task42extra-NN-V2` 的当前研究投入，将一个 Codex 工作区转给 Task43。
这表示当前候选缺乏足够继续投入的效果证据，不表示已证明全部神经方法或全部混合方法不可能有效。
两个远程分支的冻结身份如下；停止计算、回收工作区与删除唯一研究证据是不同动作。

| 研究线 | 固定远程身份 | 当前实际方法与结果 |
|---|---|---|
| Task42 | `task42_neural_coarse_inverse` @ `81c049e09a61efa38f8c7a6a762f02e8835c9b3f` | 已推进到 phase-FE 候选；不能仍概括为只在训练 NN coarse inverse |
| Task42extra | `task42extra_feinn_5nm` @ `8bf3241713e2ddd24986126f348f766d9262d346` | 5 nm、384 hex、p3 的当前 FTT/FEINN solver family 已有明确关闭结论 |

### 2.2 支持停止的具体证据

| 证据 | 实测或状态 | 可以得出的结论 |
|---|---|---|
| [Task42 V78 results][nn-v78] | FGMRES 128 步，完整物理 FE 相对残差 `0.284024612789`；`EFFECTIVENESS_FAIL` | 当前阶段未形成可用求解结果；该数值不是 E/H 场误差，也不是成功加速比 |
| [Task42 V79 response][nn-v79] | 后续 saved-field consumer 两次 CPU 准入拒绝；`NOT_RUN_CPU_GATE` | V79 只补准入/消费诊断，没有新的方法效果实验；不能将准入失败算作新的数值反例 |
| [Task42extra V47 response][nnextra-v47] | actual residual `0.346345909527` | 尚远离 formal field gate；不能用训练 loss 替代方程残差 |
| 同一 V47 | scattered E/H 误差约 `0.0646224 / 0.0646542`；energy defect `0.0227391277424` | 输出与能量仍未达到任务精度；R/T/A 只可按诊断处理 |
| 同一 V47 三步 probe | 相对改善 `8.66308290305e-8`，远低于原 `1e-3` 效果门 | 当前局部推进趋于停滞，有依据结束这条 solver family |
| 同一 V47 结论 | `CLOSE_CURRENT_FTT_SOLVER_FAMILY / NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE` | 接受当前路线关闭；不把关闭范围扩大为所有 NN 研究 |

### 2.3 证据保留与工作区改用

| 动作 | 本任务采用的规则 |
|---|---|
| 保留内容 | 固定 commit、最后 response/review、结果 JSON、失败与成本记录，保留能够追溯旧运行的入口 |
| 分支清理 | 本轮先结束研究投入；若以后删除普通分支，必须先有可访问的归档 ref，不能只依靠文档中的 SHA 长期保活对象 |
| 新任务来源 | 从 Task40para 建立 Task43，不从 NN 工作分支继承无关实验改动 |
| 建议复用目录 | `/home/fenics/Projects/NN-Lab-V2`，但先确认 dirty files、未推送提交、worktree 关系与活跃任务 |
| 未完成的现场检查 | 本次远程审计没有读取工作站目录，也没有停止现存服务或覆盖本地文件 |

这项选择回收的是后续开发与计算精力；已有负结果仍是避免重走旧路的重要输入。

## 3. 历史 hp 资产与选择性迁移

### 3.1 历史工作已经走到哪里

| 阶段与证据 | 已有能力或正面结果 | 没有证明的内容 |
|---|---|---|
| [Task33 outcomes][hp33] | 高阶固定 p 的 same-accuracy 对照与 hybrid 基础 | 原 adaptive 范围转移；不是自动 hp 闭环成功 |
| [Task35 review V6][hp35] | actual discrete DWR、周期四面体研究和同阶 adaptive 正信号 | strict R00/R 的完整 same-error replacement 尚未证明 |
| [Task35b outcomes][hp35b] | 组装时静态凝聚、预分配、张量复用与因子生命周期的真实收益 | 预算内最强候选仍只达 10/12 power 与 10/12 amplitude；不是完整精度通过 |
| [Task35d outcomes][hp35d] | 真 local h、真 local p、active-only 编号、exact sequence、hanging/Floquet、MPI 资格化 | 物理候选未全目标通过；automatic cycles 1–4 没有完成 |
| [Task35e review V1][hp35e] | 多层 local h、2:1/周期/材料闭包、variable trace、参考认证 | `PARTIAL_WITH_CONTROLLED_NEGATIVES_CLOSED`；无接受的完整 blind hp transition，迭代路线未运行 |

Task35b/d/e 的文件均从 Task35e 固定快照 `f0f10be9268ca9348ed7f40fb2237fbcd5474252` 读取。
旧 Task35b 名称不作为仍存在的远程 ref；后续抽取代码应使用固定 SHA，而不是凭记忆拼旧 branch 名。

### 3.2 现有实现是自定义 H(curl) 约束空间

现有 local p 采用 Basix 局部基与实体插值矩，在 p6 载体上构造 active edge/face/cell 空间，再进行约束、组装和凝聚。
它不是一个已经支持任意 cellwise p 的 DOLFINx runtime 开关，也不能假设低阶自由度就是高阶系数的前缀。
合格历史范围主要为 p4/p5/p6，必须满足相邻实体阶次闭包以及 gradient/curl exact-sequence 检查。

| 基线中已经存在的资产 | 最小入口 | Task43 使用边界 |
|---|---|---|
| exact-sequence variable p | [`src/adaptivity/exact_sequence_variable_p.py`][src-exact] | p3 是本次显式扩展与资格化工作；已有固定 p3 不等于已有 p3 local hp |
| dyadic refinement 与 broken mesh | `src/adaptivity/dyadic_hexa_refinement.py`、`dyadic_hexa_broken_mesh.py` | 已有真局部一分八；方向性局部分裂尚不能按现成能力承诺 |
| hanging 与复约束图 | `hcurl_hanging_trace.py`、`hcurl_trace_constraint_graph.py` | 保留切向约束、方向变换和复 Floquet 系数；不能当标量节点插值处理 |
| entity 与周期轨道映射 | `variable_p_entity_map.py`、`variable_p_periodic_orbits.py` | active mode 全局编号与周期一致性可复用 |
| 局部 variable-p 算子 | `src/solvers/hcurl_variable_p_local.py` | 复用合法局部展开和凝聚；保留局部载体内存成本 |

上表八个文件在 [Task40para 基线源码树][base-tree] 与 [Task35e 固定源码树][hp-tree] 中具有相同 blob。
这意味着不必重写这些组件，也不应把已经继承的代码再次整包迁入。

### 3.3 基线只含较早 local-h 路线，多层增量须单独抽取

| 文件或入口 | Task40para 的实际限制 | Task35e 可选择性参考的增量 |
|---|---|---|
| [`stage4_local_h.py`][src-localh] 的 `_build_forest` 与 plan loader | `maximum_level == 1`；固定 trace 路线，局部 interior override 有限 | [`stage4_local_h.py` @ 35e][src-localh35e] 的 `_build_multilevel_forest`、catalog 与 refinement-plan payload |
| `hcurl_broken_trace_graph.py` | 较早固定 trace 图 | [35e 图实现][src-graph35e] 的 `_variable_trace_degree_maps` 与 `build_broken_hexa_entity_degree_arrays` |
| `hcurl_broken_cell_trace.py` | 较早 leaf/cell 路由 | [35e cell-trace 实现][src-cell35e] 的 `build_broken_hexa_cell_trace_constraint_map` 与多层实体处理 |
| `variable_p_transfer.py`、assembly/reduction | 仍存在全向量 gather 与旧接口 | 按实际调用需要抽取 selected-row PETSc scatter、dual/primal 转移；不复制整个 shadow/controller 层 |

多层计划加载、实体阶次图和 cell-trace 路由是一组兼容性改动；不能只拷一个同名函数后宣称多层已支持。
先让一层合法 h/p 闭环运行；确需第二层时再抽取上述最小依赖，逐项验证新增能力。

### 3.4 必须先承认的工程限制

| 限制 | 对 Task43 的处理 |
|---|---|
| 旧 local h 为 affine hex、矩形块几何、x/y Floquet、无 PML | 新 phi90 的几何分面、材料标签、周期伙伴和非平凡双向相位必须重新检查 |
| 一分八会连带周期/材料/2:1 闭包 | 报告真正新增 leaves、active FE、trace rows；不能只按 requested cells 估成本 |
| structured axis-plane 细化不是真 local h | 可作对照，但不得把整层加密包装成局部方向自适应 |
| p6 载体局部 tensor 为 882×882 | active rows 降低不保证组装或峰值内存同比降低；记录载体与 active 空间两份成本 |
| 两处旧 90,000 active-FE 硬限制 | `build_stage4_local_h_reduction_authority` 与 `build_variable_p_assembly_time_reduction` 需使用 Task43 明确预算；不冒用 Task35e scope |
| 全量 `comm.allgather` 路径仍存在 | 小规模校准可先用；进入 0.7 nm 前审计转移、恢复、元数据复制与实际峰值 |
| [DtN port 实现][src-dtn] 明确排斥 variable p + never-materialized port | 已有 assembled auxiliary Fourier-DtN 可作起点；BAL_H/matrix-free 是独立接线工作 |
| canonical vector export 仍有 fixed-p 限制 | 自适应场与完整输出需真实恢复/映射，不得静默退回固定 p 或丢失通道 |

两处预算限制与分布式行为可从 [reduction 源码][src-reduction]、[assembly 源码][src-assembly] 和 local-h 入口核验。

### 3.5 复用数值核心，不恢复旧的大型控制框架

| 旧负结果 | Task43 必须采取的不同做法 |
|---|---|
| p5 trace / p4 interior 的旧试验缺失 gradient modes | 候选空间先过 exact-sequence 资格；无效空间不能当方法精度负例 |
| 几何距离驱动 remote-air p-down 使输出恶化 | 初期从粗到细；先不做 p-down，也不把“远离材料”当低误差证明 |
| Task35e full-shadow 单元归因不能预测 selected-action 端点响应 | 指标仅用于选择候选，接受必须消费该候选真正的 PDE 解 |
| 四 cell p 动作有 25/59 目标方向相反；单 cell 有 30/59 方向相反 | 保留预测与实测对照，不把 DWR 分解硬解释成局部动作收益 |
| 16-face-orbit 优化目标过关，但十个旁路输出越界 | 每次验收覆盖完整输出集；不能只盯选中的目标或 R/T/A |
| Task35e 无 accepted transition，且 controller/hidden-auditor 扩张已关闭 | 只写短的 solve–estimate–mark–solve–accept 循环，输出普通记录和网格/阶次图 |

旧任务的 59 个目标属于老 13.5 nm、10° grazing、y 不变模型，不可原封不动套到新 phi90 几何。
Task43 必须重新固定新几何的通道全集、复振幅、场量、能量和误差尺度。

## 4. dot 分支提供的具体教训

### 4.1 报告与代码的身份要分开

dot 最新 hp 证据位于 `docs/task40extra_dot_parallel_cloud/reports/hp_reference_free/`，不能只查看编号最高的旧 `response_v15`。
[上传边界说明][dot-boundary] 指明此次仅上传报告；科学 checkout 为 `322e62e11a80969b3a35f0cbb08b25c11c539ea6`。
新 hp overlay、runtime、recipe 和完整审查脚本没有随报告上传；固定报告 HEAD 不是完整可恢复执行包。

| dot 证据 | 已经支持的结论 | 尚未支持的结论 |
|---|---|---|
| [96-cell coverage progress][dot96] | 16×2×3、全 p6；64,512 independent FE、21,392 凝聚未知量含 80 ports；full-active residual 约 `4.44e-12` | 工作解可接受，不等于离散收敛；仍缺第二独立 h 实解及更强盲区检查 |
| 同一报告的覆盖审计 | 72→96 的 R/T/Av 差约 `5.18e-8 / 4.73e-8 / 4.60e-9` | 小总量差不能替代局部场和新单元覆盖；旧 144-panel 检查未覆盖 96 网格全部新单元 |
| 同一报告的成本 | 捕获/求解/恢复约 219.20 s；九个成功阶段约 1167.60 s，另有失败成本 | 不能只报最后 solve；该成功采用 global sparse LU，未证明 BAL_H 扩展性 |
| [324-cell recovery report][dot324] | 新恢复合同下 FGMRES 实际完成 56 步，监督约 601.25 s | 600 s TIME_LIMIT 后没有 accepted field、R/T/A 或 final packet |
| 同一 324-cell 记录 | 最后完整 native 检查在 48 步，残差 `0.02164289779701526` | 56 步 `0.02097352549` 只是递推值，不能冒充最新独立真残差 |

### 4.2 Task43 应采用的修正

| dot 教训 | Task43 的落实方式 |
|---|---|
| [phase2 实际动作][dot-phase2] 的 p+p、h-x 真 solve 改善远小于投影指标暗示 | enriched/projection 只负责排序；真正候选求解、完整误差和实际新增成本决定是否接受 |
| [方向选择修正][dot-direction] 显示 `max(x,y,z)` 会把 x 缺陷错误归给 z | 每个方向使用自己的指标，并按闭包后的新增 FE 归一；新 phi90 不硬编码旧 x 优先 |
| 324-cell 新合同把旧 native-cross identity 降为 diagnostic | 明示任何验收合同变化；不得称普通修 bug 后自动继承旧 qualification |
| 同 raw trace 通过不等于 native 解收敛 | 恢复一致性、方程残差、离散误差分别报告；一项 PASS 不能替另外两项授予资格 |
| 只有 0/8/32 retained 向量耐久，56 步未完整落盘 | 保存状态和已发生费用分别记账；重启不能删除未耐久的已执行成本 |
| 600 s 是旧运行的具体限制 | Task43 根据新工作量和现场资源预算执行，不把旧短 timeout 复制成默认科学停止条件 |

dot 说明部分路线值得借鉴，同时说明“投影更好”“迭代残差下降”和“自适应求解成功”必须分开判断。

## 5. 新任务与旧失败的区别、未运行边界

### 5.1 本次范围更具体，但不预承诺成功

| 项目 | Task43 的计划与验收含义 |
|---|---|
| 新物理对象 | 先在新 phi90 原尺寸 13.5 nm 模型工作；旧 y 不变模型的误差与方向结论只作历史输入 |
| 粗起点 | 优先审查 180-cell、p3 候选；p3 local-p/trace/hanging/transfer 是新增资格，不能仅换配置 |
| 桥接点 | p4–6 用作已有数值核心与原 solver 的连接对照；不能用桥接通过冒充 p3 扩展完成 |
| 闭环 | current solve → richer witness/估计 → 合法 h/p 动作 → actual candidate solve → 全目标 accept/reject |
| 初期目标 | 取得 2–3 次真实 accepted transitions，并保留拒绝记录；仅有计划/标记/一次 shadow 不算完成 |
| 动作覆盖 | 不强迫每轮同时 h 和 p；需要有真实 local h 与 local p 的独立资格及候选实测 |
| 独立见证 | 使用足够丰富、覆盖新单元的独立 witness，避免同一缺陷空间相互“验证”；明确它仍是离散参考 |
| 同精度比较 | 使用同一新模型、同一输出误差合同的 uniform controls；先确认闭环有效，再比较成本 |
| 成本口径 | 包含失败、witness、组装、凝聚、转移、预条件器重建、恢复和输出；同时报告最终单次 solve |
| 迭代接线 | 在同一自适应离散上与 direct 对照，重建约束/active trace/port/PC；独立检查原始方程残差 |
| 代数误差 | 将求解误差控制在离散判据以下；必要时用一次更紧容差对照判断是否污染标记 |
| 扩大规模 | 13.5 nm 闭环及 iterative gate 之后，再评估 0.7 nm；不把小规模 direct 当短波生产解法 |

Task35e 也试过更简单的 broad p/h 推进，因此“换成从粗到细”本身不是新的成功证明。
本次合理性在于新模型、明确的起点与有限闭环、真实候选验证、完整输出和独立迭代资格，而不是承诺某个固定压缩倍数。
常规接口、路径或作用域 bug 应在原合同内修复后继续；若必须改变科学验收含义，应单独记录依据与适用范围。

### 5.2 本文结束时的状态

| 项目 | 状态 |
|---|---|
| 远程基线、历史文档和关键源码读取 | 已完成本次只读审计，以上均引用固定 SHA |
| Task43 p3 扩展与新模型组件资格 | NOT_RUN |
| 180-cell 新模型 PDE、rich witness 与均匀对照 | NOT_RUN |
| Task43 accepted h/p transitions | 0；尚无新的科学结果 |
| Task43 variable-p + BAL_H/matrix-free | NOT_QUALIFIED；不能由历史 fixed-p 结果转授 |
| 工作站目录复用与活跃进程检查 | NOT_CHECKED；由工作站 Codex 在开始前执行 |
| NN 分支与旧负证据删除 | 本文不执行删除；应保留可访问归档后再做独立清理 |

本审计的作用是确定可复用起点和必须补做的工作；后续状态只由 Task43 的实际执行回执更新。

## 固定来源

[base-commit]: https://github.com/Rookie1234567/MyFEniCS/commit/405e3aff42ac421a4c99315df1ed9b96941ecbe4
[base-tree]: https://github.com/Rookie1234567/MyFEniCS/tree/405e3aff42ac421a4c99315df1ed9b96941ecbe4/src
[iter-commit]: https://github.com/Rookie1234567/MyFEniCS/commit/59722cca5e35eac65efead9fd27f7d7fc0c70419
[iter-v9]: https://github.com/Rookie1234567/MyFEniCS/blob/59722cca5e35eac65efead9fd27f7d7fc0c70419/docs/task41extra_phi90_p50x50_g17x20/outcomes/v9_preparation.md
[para-summary]: https://github.com/Rookie1234567/MyFEniCS/blob/405e3aff42ac421a4c99315df1ed9b96941ecbe4/docs/task40para_phi90_mesh_modes_direct/outcomes/summary.md
[para-comparison]: https://github.com/Rookie1234567/MyFEniCS/blob/405e3aff42ac421a4c99315df1ed9b96941ecbe4/docs/task40para_phi90_mesh_modes_direct/outcomes/records/d15_y5_1_y6_siblings_saved_output_comparison_20261021_v1.json
[para-bz]: https://github.com/Rookie1234567/MyFEniCS/blob/405e3aff42ac421a4c99315df1ed9b96941ecbe4/docs/task40para_phi90_mesh_modes_direct/outcomes/records/d15_b_z1_z2_saved_output_comparison_20261022_v1.json
[nn-v78]: https://github.com/Rookie1234567/MyFEniCS/blob/81c049e09a61efa38f8c7a6a762f02e8835c9b3f/docs/task042_neural_coarse_inverse/outcomes/records/results_v78.json
[nn-v79]: https://github.com/Rookie1234567/MyFEniCS/blob/81c049e09a61efa38f8c7a6a762f02e8835c9b3f/docs/task042_neural_coarse_inverse/response_v79.md
[nnextra-v47]: https://github.com/Rookie1234567/MyFEniCS/blob/8bf3241713e2ddd24986126f348f766d9262d346/docs/task042extra_feinn_5nm/response_v47.md
[hp33]: https://github.com/Rookie1234567/MyFEniCS/blob/f0f10be9268ca9348ed7f40fb2237fbcd5474252/docs/task033_high_order_floquet_hybrid_hp_adaptivity/outcomes/summary.md
[hp35]: https://github.com/Rookie1234567/MyFEniCS/blob/81c714b236e9c362df8783382f1d40a5cd888cd5/docs/task035_hcurl_goal_oriented_adaptivity/review_report_v6.md
[hp35b]: https://github.com/Rookie1234567/MyFEniCS/blob/f0f10be9268ca9348ed7f40fb2237fbcd5474252/docs/task035b_high_order_local_hp_resource_envelope/outcomes/summary.md
[hp35d]: https://github.com/Rookie1234567/MyFEniCS/blob/f0f10be9268ca9348ed7f40fb2237fbcd5474252/docs/task035d_goal_oriented_exact_sequence_hp_adaptivity/outcomes/summary.md
[hp35e]: https://github.com/Rookie1234567/MyFEniCS/blob/f0f10be9268ca9348ed7f40fb2237fbcd5474252/docs/task035e_reference_blind_multilevel_hp_adaptivity/review_report_v1.md
[hp-tree]: https://github.com/Rookie1234567/MyFEniCS/tree/f0f10be9268ca9348ed7f40fb2237fbcd5474252/src
[src-exact]: https://github.com/Rookie1234567/MyFEniCS/blob/405e3aff42ac421a4c99315df1ed9b96941ecbe4/src/adaptivity/exact_sequence_variable_p.py
[src-localh]: https://github.com/Rookie1234567/MyFEniCS/blob/405e3aff42ac421a4c99315df1ed9b96941ecbe4/src/adaptivity/stage4_local_h.py
[src-localh35e]: https://github.com/Rookie1234567/MyFEniCS/blob/f0f10be9268ca9348ed7f40fb2237fbcd5474252/src/adaptivity/stage4_local_h.py
[src-graph35e]: https://github.com/Rookie1234567/MyFEniCS/blob/f0f10be9268ca9348ed7f40fb2237fbcd5474252/src/adaptivity/hcurl_broken_trace_graph.py
[src-cell35e]: https://github.com/Rookie1234567/MyFEniCS/blob/f0f10be9268ca9348ed7f40fb2237fbcd5474252/src/adaptivity/hcurl_broken_cell_trace.py
[src-reduction]: https://github.com/Rookie1234567/MyFEniCS/blob/405e3aff42ac421a4c99315df1ed9b96941ecbe4/src/solvers/hcurl_variable_p_reduction.py
[src-assembly]: https://github.com/Rookie1234567/MyFEniCS/blob/405e3aff42ac421a4c99315df1ed9b96941ecbe4/src/solvers/hcurl_variable_p_assembly.py
[src-dtn]: https://github.com/Rookie1234567/MyFEniCS/blob/405e3aff42ac421a4c99315df1ed9b96941ecbe4/src/solvers/dtn_port_3d.py
[dot-tree]: https://github.com/Rookie1234567/MyFEniCS/tree/a9b21d8a79d70c3b3ad1a62e748872af11ff0f79/docs/task40extra_dot_parallel_cloud/reports/hp_reference_free
[dot-boundary]: https://github.com/Rookie1234567/MyFEniCS/blob/a9b21d8a79d70c3b3ad1a62e748872af11ff0f79/docs/task40extra_dot_parallel_cloud/reports/hp_reference_free/2026-10-13/README.md
[dot96]: https://github.com/Rookie1234567/MyFEniCS/blob/a9b21d8a79d70c3b3ad1a62e748872af11ff0f79/docs/task40extra_dot_parallel_cloud/reports/hp_reference_free/2026-10-13_uniform36p6_progress/current96_coverage_progress_zh.md
[dot324]: https://github.com/Rookie1234567/MyFEniCS/blob/a9b21d8a79d70c3b3ad1a62e748872af11ff0f79/docs/task40extra_dot_parallel_cloud/reports/hp_reference_free/2026-10-15_native324_recovery_checker/report_zh.md
[dot-phase2]: https://github.com/Rookie1234567/MyFEniCS/blob/a9b21d8a79d70c3b3ad1a62e748872af11ff0f79/docs/task40extra_dot_parallel_cloud/reports/hp_reference_free/2026-10-13/phase2/phase2_summary_zh.md
[dot-direction]: https://github.com/Rookie1234567/MyFEniCS/blob/a9b21d8a79d70c3b3ad1a62e748872af11ff0f79/docs/task40extra_dot_parallel_cloud/reports/hp_reference_free/2026-10-13_uniform36p6_progress/directional_h_selection_correction_zh.md
