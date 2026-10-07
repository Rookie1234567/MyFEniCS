# Task041 Review V10（复审修订）：保留5 nm提速，优先交付0.7 nm pilot与2 nm阶段容量

## 0. 本次复审事实、决定与身份

**2026-10-08再次访问原Task041分支，远端仍为上一版Review V10提交 `e217541d8d45b555eabd7070e808acbf764ae053`；数学源码仍为 `5025fdd31a1edc4ce34a8df3150a12ca90009c01`，最新response仍为V11，outcomes树仍为 `276be4a319bf248a933113c2161425fb190e00be`。没有新增已推送的V10运行结果或Response V12。** 这不能证明工作站未工作；只能说明本次没有新的实测可供审阅，不得把旧16.64 h再次包装成新增成绩。

依根AGENTS第15节，本次直接修订尚未收口的V10，用普通commit保存前版历史，不另建V11/addendum，不重置已有运行、费用或资格。此次ChatGPT仅修改review与交接文本，没有运行PDE、停止进程或修改工作站。

**执行决定：已成功的fixed-H6按需模态反馈＋准确p4凝聚/BAL_H继续作为基线。优先完成已注册的0.7 nm缩减pilot；真实2 nm通过明确可执行的阶段容量检查推进。缓存及其他性能优化不再成为这两项的共同前置任务。普通接口bug局部修正后继续，原方程/物理/内存安全不放宽。**

```text
repository                 = Rookie1234567/MyFEniCS
working_branch             = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date                = 2026-10-08, Asia/Singapore
review_revision            = V10-r2; replaces working text, keeps prior Git history
reaudited_remote_HEAD      = e217541d8d45b555eabd7070e808acbf764ae053
reviewed_numerical_base    = 5025fdd31a1edc4ce34a8df3150a12ca90009c01
base_latest_code_commit    = Add opt-in matched W0.7 axial cell policy
previous_review            = review_report_v9.md
latest_response            = response_v11.md
response_required          = response_v12.md
qualified_W5_source        = d6fe6b2b239896e66d8c5d1bf9b8a0e45931a561
qualified_W5_invocation    = 2539de4d129f41e2ac49536bfd3b6fde
batch                      = task041_v10_measured_shortwave_progress
default_candidate          = fixed_h6_modal_gmres_research + cell_condensed p4
swap_policy                = task041_v8_swap_observe_continue
execution                  = MPI8 x 1, frozen physical-core map, socket0/node0
ordinary_default           = unchanged
master_merge               = NOT_APPROVED
```

最终目标仍是**0.7 nm、目标50×25 nm周期单胞、约2 TB物理内存、有系统余量、48 h完整计算**。完整时间含QEP、FE/PC构建、求解、恢复、核验和清理；warm-consumer与研发费用分列。Hybrid内部必须满足模态传播假设，不等同于任意非可分三维Full3D通过。通用Full3D仍需分布式、matrix-free和可扩展预条件架构。

### 0.1 本次修订消除的执行歧义

| 修订点 | 本轮要求 |
|---|---|
| 没有新推送结果 | 接续原V10，不要求重新开始、不虚构新状态；先公布本机真实阶段 |
| P1/P2/P3的顺序 | 已有健康作业继续；否则优先pilot。W2阶段容量与pilot串行重负载，附加优化不挡住二者 |
| symbolic分析接口 | 先用本机小矩阵证明能在numeric前停住，不能将PCLU的完整setup当成仅symbolic |
| 原始资源公式的适用阶段 | host整场启动门只在启动评估；运行中检查阶段新增需求及冻结cap，不重复扣本job已占内存 |
| matched-cell验证 | 优先复用现有真实FE拼接测试，不新造框架；均匀正入射控制不能冒充W光栅全部模态资格 |
| 后处理失败 | 已封存的合格解优先只读重验或恢复；不为schema、报告或坐标错误重算QEP/线性求解 |
| 阶段交付 | 一个当前runroot、一个当前blocker和下一动作；至少交实际PDE/容量证据，而非又一轮注册测试 |

此修订沿用V9/V10对exact-only、MPI1-only、0.7禁跑和swap硬门的显式覆盖，不回写旧task。授权有限阶段容量测量不等于授权未知大分配；不提高旧case硬cap、不降低384 GiB节点floor、不启用node1、不变更普通默认。主控/执行内部审核照旧，用户不必逐项重复批准相同范围。

## 1. 现有结果的裁决：5 nm已加速，短波长仍待实测

依据本base的[Response V11](response_v11.md)、[summary](outcomes/summary.md)、[V9 outcome](outcomes/hybrid_0p7nm_2tb_48h_v9.md)、[W5 record](outcomes/records/task041_v9_fixed_h6_public_5nm.json)与[W2解释记录](outcomes/records/task041_v9_w2_h3_interpretation_correction_20261007.json)。早期快照和后续注册状态按source/时间分开。

| 项目 | 原逐列路线 | fixed-H6已完成W5 | 裁决 |
|---|---:|---:|---|
| 模型 | W、5 nm、p6/h4、M480、MPI8 | 相同冻结物理/离散 | 研究候选，不是连续解资格 |
| 预构建正式侧区响应 | 1920 | 0 | 不物化全列Schur，原方程不变 |
| outer / 侧区内部总步 | 5 / 30296 | 49 / 7732 | 不能仅按outer步数评性能 |
| p4 backsolve / refinement | 89237 / 28645 | 27097 / 11633 | rank复制计数不乘MPI8 |
| public至finalizer | 202124.563261555 s | 59914.951233018 s | 56.146→16.643 h，描述性约3.3735倍；两场非隔离，不作单因素因果声称 |
| process-tree RSS峰 | 43415531520 B | 42573258752 B | 约43.42→42.57 GB；新场在53221163008 B cap内 |
| 新场原五残差 | — | 最大4.87285789944735e-9 | 各<=5e-9通过，bottom接近门限不等于失败 |
| 新场物理/收尾 | — | 原recovery/physics与10项finalizer通过 | 已完成，无需重跑16 h来补元数据 |

新场原残差分别为global `8.573354680237858e-10`、bottom `4.87285789944735e-9`、top `4.3588733213657296e-10`、modal `3.0159774145340474e-9`、reported `8.573351523834966e-10`。R/T/A/A_volume分别为 `0.7331842734229947 / 0.00022009869546076797 / 0.2665956278815445 / 0.2665962726246991`，closure `6.447431546430238e-7`。专属cgroup峰 `41376940032 B`、job swap0与tree峰分列；旧producer资源缺测不否定已验证packet的数值身份，也不能补造producer资源PASS。

**仍未取得的新证据：** W2 fixed-H6真实容量/完整场，0.7 pilot真实producer/consumer终态，以及原50×25 nm目标的h/M/容量/48 h资格。0.7已注册、producer-root路由和matched-cell代码已存在，不再沿用早期 `registered=false` 作为当前阻塞。代码存在不是已运行。

### 1.1 P0只读收口，不追加PDE

W5 record的部分 `current_minus_reference_T/A` 与所列原值不一致。按记录原值新减旧，R约 `+3.54384e-11`、T约 `-2.6720737e-13`、A约 `-3.51712e-11`、A_volume约 `+1.7145e-12`。先核对双方原summary/source/hash，另写可追溯派生更正；不得直接覆盖成猜测，也不重算PDE。40位Git SHA不因字段误叫 `source_sha256` 而变成64位文件hash。

复用已存W5与10月3日参考的E/H、canonical、600通道复振幅/功率和normal flux做同离散离线比较。`integrated_full3d_checker=not_available`不是这项Hybrid比较的同义词。旧资源不完整不否决数值项；旧数组确实缺失则明确partial，不伪造通过。checker/root/schema错误修完读取同一封存artifact，不能再次运行QEP或完整求解。

## 2. 当前时间成本与优化方向

固定H6仅替代预条件器内部的模态反馈：

```math
\widetilde S_Hv=Cv-L_bJ_bH_{6,b}J_b^HG_bv-L_tJ_tH_{6,t}J_t^HG_tv.
```

H6是固定正定辅助作用，不是磁场或准确Maxwell逆；LDU其余位置仍用准确p4凝聚/BAL_H支持的侧区FGMRES。原Hybrid A和f不变。FGMRES允许非线性PC，不意味着可把非线性近似作用当原线性MatMult。[S1]

新W5有196次实际侧区响应，平均约39.45个内部步/响应；outer inclusive为 `57734.113258151 s`，约占总wall96.36%。setup约2110.216 s，恢复约59.013 s。`57734/7732≈7.467 s`包含模态/正交化/检查，不能写成纯kernel单步时间。现阶段不再优化旧1920列容器。

48 h预算必须同时考虑迭代数量和每步成本。仅作条件算术：若W2仍需7732步、QEP仍按旧29504.116 s，则48 h扣QEP后，忽略其他费用也仅剩约18.53 s/步。旧W2约100 s/步不能由W5的3.37倍描述性收益自动消除。这不是新W2的预测，更不是其失败结论。

因此先取得新W2及真实0.7的计数/耗时。现成route-plan/leading-PH复用是可选低风险后续，不是先把5 nm压到几小时才允许启动短波长。保持fixed-H6主线；只有短波长实际停滞或总工作明显失控时，才进入§6唯一备选。

## 3. 执行顺序：一个当前工作流，先出真实结果

启动时核对本机branch/HEAD/upstream/dirty、保护stash、当前unit/InvocationID/PID/starttime、source、runroot及阶段。已有健康且在授权范围内的作业继续，不为同步本次文档强杀、重启或热改源码。尚未推送的实际结果先出小型record，不用“远端没有”推断本机没做。

| 顺序 | 工作与退出证据 | 连续推进规则 |
|---|---|---|
| P0 | 当前运行快照、旧W5离线比较/派生更正 | 轻量工作不阻塞已准备的真实运行 |
| P1优先 | 已注册W0.7 reduced的最小必要接线/离散验证，随后producer→consumer→完整场与finalizer | 不等待新缓存、W2双侧峰或pilot的网格收敛研究 |
| P2 | W2实际mesh/矩阵库存→阶段分析→可支付的factor→真实求解 | 已有W2健康作业则优先继续；与P1不并发重负载 |
| P3条件 | 同factor少量真实RHS验证缓存，再最多一个净热点 | 无收益或准备不足用已通过基线，不让此项挡住P1/P2 |
| P4条件 | pilot相邻h/M点、W2容量/耗时校准、一个必要中间尺度或目标规模 | 一次只改一个可解释的离散因素；不能直接跳最大0.7模型 |

**默认先P1；只有W2已经在健康运行，或P1存在暂时无法绕过的真实物理/资源问题且P2某阶段已可支付时，才调换。** 确定首个实际阶段后不要反复在两条线间改计划。两项可并行编辑/只读核查，但重型矩阵、QEP、PDE必须串行。其他项目的heavy不属于停止授权；无可用窗口时记录外部资源阻塞并完成轻量工作，不擅自终止、迁移或抢占邻任务。

普通路径、profile/CLI、empty-owner、坐标、schema、账本和finalizer错误，保存失败→最小修正→受影响实际调用链测试→自行继续；不每遇一处错误就结束整轮等待用户。未修正的原方程、残差或物理错误不得放行。同根因连续两次仍失败，第三次必须先降为最小fixture定位，禁止原样重复大构造；其他独立、安全工作继续。已有费用不清零。

## 4. W2阶段容量：必须能够停在下一笔大分配之前

### 4.1 身份与可用量

保持W、2 nm、p6/h1.5、M1200、MPI8、cell_condensed、fixed-H6、P4 target5e-13及最多两次修正。复用对应旧TOAR packet，沿原validator/hydration核验；若公共W2 guard尚未透传，授权现有注册范围内的窄修复，不新增第二runner。`side_residual_correction_steps=1`不是p4 refinement次数。

10月7日host MemAvailable约2.071 TB、node0 MemFree约854.605 GB，node0扣384 GiB floor后约442.288 GB。这是历史样本，不是现在准入。保护stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976`中的node0门未应用；查实际代码与策略，不整包应用stash，不称其已在运行。

旧642.45–647.90 GB峰来自不同后端/阶段，既不是新后端必需量，也不因删Schur列就自动消失。区分最终侧区p4因子、one-cell traction的临时精确因子和其他构造因子，逐对象记录出生/销毁。独立QEP producer已退出时，其峰与consumer峰取最大，不相加；packet加载的驻留副本仍属于consumer。

### 4.2 阶段式准入授权及实际调用次序

**整场峰未知时，允许先做已经可预算的mesh/constraints、矩阵/缓存形成和symbolic分析；不允许跨越未知大分配直接numeric factor。** 分级顺序必须服从真实call graph：若one-cell traction因子早于两侧p4因子构造，它就是更早的阶段门；不得画出错误顺序后在内部偷偷完成分解。

每个实际大对象按：预分配库存→装配→symbolic→读取估计→numeric→驻留核验→下一对象。用当前矩阵结构和已校准模型估计下一阶段，而非用W5全树RSS乘比例。PETSc rows/NNZ、MUMPS INFO/INFOG/RINFOG的单位、scope和编码须按安装版解释；0、负数或缺失不得默认0字节。symbolic本身也消耗内存，必须预算其图结构/工作区。[S2–S3]

### 4.2.1 本机symbolic能力先用小矩阵核验

本次复审发现的是**接口可执行性风险，不是已测工作站bug**：PETSc C提供 `MatGetFactor → MatLUFactorSymbolic → MatLUFactorNumeric`，但公开petsc4py文档把 `factorSymbolicLU` / `factorNumericLU` 标为 `Not implemented`。不能仅凭Python属性存在就认定可用。`PCFactorSetUpMatSolverType`只取得factor对象，不等于完成symbolic；PCLU的普通setup路径包含numeric，不能将 `KSP.setUp()`/`PC.setUp()`笼统当成安全的analysis-only。[S7–S10]

在原生complex128/MPI ABI下，先用一个小型非Hermitian复矩阵验证实际路径，记录installed version、调用边界、analysis完成/ numeric未进入证据，以及拒绝numeric后的全rank清理。优先复用仓库已有原生桥；确实缺失时允许一个使用当前PETSc公开C API与正确头文件/ABI的最薄分析桥及focused tests。不得猜私有结构、用错误句柄、升级PETSc、换MPI、增加第二套MUMPS或新造通用求解框架。

native分析暂不可用，不得用一次完整W2 numeric作为探针。先完成可支付的真实rows/NNZ/内存库存，提交明确的“哪一调用不能分离、已测到哪一对象、下一额外需求和缺口”，修复该局部接线；同时继续P1。不再将整个结论停在 `new_peak=unknown`。symbolic估计是预测而非严格RSS上界，需包括pivot/工作区余量与非MUMPS并存对象。

### 4.3 不重复扣减已用内存

启动时冻结总cap `B_cap`，取case硬上限、规划线、节点总量减floor、启动节点可用量减floor，以及可用父/专属cgroup限制的最严者。父cgroup还有其他占用时扣除实际剩余额度，不只读其裸上限。继续保持原384 GiB node0 floor及host安全余量，不借2 TB名义提cap。

每次大分配前，`B_live`为本job当前同scope驻留，`Delta_next`为下一阶段新增对象及临时高水位，`W_margin`为有依据的未覆盖余量，`F0_now`为当前node0 MemFree：

```math
B_{\mathrm{live}}+\Delta_{\mathrm{next}}+W_{\mathrm{margin}}\le B_{\mathrm{cap}},\qquad
\Delta_{\mathrm{next}}+W_{\mathrm{margin}}\le F_{0,\mathrm{now}}-R_0.
```

host当前余量另查，新增分配后仍须保留已批准host reserve。仅确实已释放且采样确认的对象可减少当前基数；计划释放不能预扣。多个互斥阶段的峰不机械相加，真实重叠不能遗漏。`F0_now`已扣本job当前占用，不能再拿 `F0_now−floor`作新的允许总RSS与 `B_live`比较。该风险用只改变字节计数的fixture验证，不伪称现场已发生double-count bug。

旧 `MemAvailable >= max(predicted_peak+256 GiB,1.70 TiB)`是整场**启动**合同，不是运行期间须反复保持1.70 TiB空闲。无分阶段证据的完整启动沿用；本节阶段式运行以该阶段保守高水位替代未知的整场预测项，运行时按冻结cap和当前reserve执行。不能因正常分配使启动前空闲量下降而错误停机；也不能恢复swap硬门。

当前矩阵numeric仍不可支付则受控退出该阶段，保留可审统计/可用工件；优先去除最大复制或生命周期重叠。不改网格、材料、M来伪称原W2已跑。两侧可支付且原检查正常后，同生命周期进入实际入射，前8步/一个restart仅为观察点，不退出重建；正常进展继续完整结果。实际长期停滞才按§6有界处理，不提高max_it或开月级盲跑。

## 5. W0.7 pilot：从已有注册和测试进入真实PDE

```text
input/official/task041/side_balh/w0p7nm_p6h0p70_m400_mpi8_cell_condensed_pilot.dat
geometry       = 10 x 5 nm; z=-2..26 nm; interfaces=2/22 nm
numerics       = p6/h0.70/M400/MPI8; fixed-H6; p4 target5e-13
candidate n_W  = 0.9995903781323069 + i*0.00012887909720587614
selected z     = 2, 7, 12, 17, 22 nm
current cap    = 53221163008 B
```

这是source-derived W材料的冻结数值pilot；位于official目录不等于已取得材料不确定度、h/M或生产资格。材料原始字节、常数/单位、密度、能量、插值区间、正吸收符号、n/epsilon和hash必须绑定。不把材料不确定度研究新增为首场启动门。

### 5.1 最小验证后连续执行，不另开验证项目

`b85d7a57`已接通validated producer-root并纠正恢复坐标；`5025fdd31`加入 `matched_uniform_axial_cell`。后者采用L20/N29，局部精确单元长度及传播步长均为20/29≈0.689655 nm，不能删除旧L100断言后继续使用10 nm局部traction。这是接口离散变化，需要独立验证，不是简单包装修补。

**当前已存在真实FE测试，不应重复开发：** `src/test/test_task037c_exact_one_cell_traction.py::test_proposed_normal_incidence_homogeneous_w_matched_h_stitch_control` 比较同轴向步长的局部端点通量与完整L20/N29直接消元，matched分支已有5e-9响应门；历史h10分支只记录差异、没有等价通过门。优先查最终数学源码/ABI下已有serial和MPI2证据；缺哪项仅补哪项，不再创建另一套三箱/拼接oracle。

该测试是均匀W正入射、常切向场控制，不使用真实选取QEP模式，不能冒充1°光栅全模态资格。生产实际路径仍需验证端点primal/dual、normal/phase、正负lam/mu、`local_h=global_h=L/N`、局部与总传播语义，并在首场保留原traction/projection/physics门；不要求预付全部400模式的独立侧区响应来资格化无逐列路线。selected-packet与fresh-basis应使用相同局部定义，不错误沿用旧source的数值算子身份。

参考平面从cfg、接口从profile读取，检查W5保持10/110而pilot为2/22；采样坐标、材料侧、normal、shape与体积分一致。使用已有公共路由/恢复测试补最小受影响断言；不能因为函数名仍含m10而另写恢复器。mock参数透传通过不等于真实FE通过，但已有真实测试也不应被忽略。

### 5.2 QEP、求解和恢复的失败边界分开

只有一个当前public run：ABI/资源→有兼容packet则原validator/hydration复用，否则registered fresh producer→确认producer退出→consumer→原五残差→封存最小recovery packet→释放factor→复E/H、R/T/A/A_volume、全部衍射→finalizer。

validated-root代码存在不表示磁盘必有packet。核实际manifest、shards、producer终态与输入兼容；不复制假封套、不改写producer source。有效QEP不因consumer bug、轴向恢复修正或纯metadata更新自动重算；但横截面离散、材料或所需模式集合改变时重新做依赖判断，不声称任意输入都能复用。

恢复/输出/checker失败时，先读取已封存的合格解与原run身份，用原恢复路径重建输出或只读重验，不重新factor或线性求解；只有恢复工件确实缺失/损坏、字段不可恢复或数学输入变化，才重跑相应最小阶段。不能承诺恢复未保存的p4因子或Krylov内存，也不能拿不满足原残差的场生成official结果。

当前pilot cap不提高，分阶段库存应覆盖one-cell临时精确构造、packet复制和两个p4因子。若限额内某阶段确实不可支付，保留已合格QEP，交最大对象和差额，继续有界存储修正/P2；不要求拆内存、开启node1或提高硬上限来推进。

### 5.3 首场先交付，再做相邻精度

首场通过立即提交真实结果及计数，不等h/M研究结束。随后独立.dat阶梯为 `p6/h0.70/M400 → p6/h0.525/M400 → p6/h0.525/M600`，各阶段先预算；不要hp×M全组合扫描。当前guard仅h0.70/N29，后续按各已注册case的实际 `N=ceil(L/h_target)`（沿用原近整数规则）及 `h_z=L/N`扩展，不能盲复用29或删除所有guard。W5/W2原策略不静默改变。

32056个目标external keys和1292个pilot keys是不同几何的派生清单，必须按实际resolved重新绑定，保留原nonpropagating/Rayleigh语义；external keys不是内部M。完整输出不能被report范围截断。首场离散解不是h/M收敛；缩减10×5 nm不是原50×25 nm目标。相同h下几何各向放大5倍，体规模示意约125倍，不能统一外推因子/trace×channel/QEP成本。

## 6. 提速只针对剩余工作，不重新发明已成功方法

W5实测 `route_plan_reuse=false`、`leading_ph_dual_reuse=false`。现有p4逆本身已经缓存部分active-trace请求计划；不要把两者混称全部缓存都未实现。先从196条原响应审计定位哪些路由/PH仍重复，以及其包含关系，不再重做已缓存的部分。

准备充分且不延误P1/P2时，底/顶各一条真实非零RHS（含一个困难方向），同布局、同factor、零初值，做原/新/新/原有限对照。缓存仅复用固定owner/索引计划或同一次PC中已证明相同的PH输入；实际值通信、ghost/周期/伴随和原A4检查保留。不跨PC以范数相同替代值相同，不让可变输入污染缓存。setup和常驻workspace计入，端到端收益不明就保留基线。

最多再选一个净热点：A4原残差作用或凝聚缩减/恢复的有界编译/批处理。**源码 `_reduce_storage_rhs` 当前在某些无内部端口项的单元仍先做 `lu_solve`，而trace修正另由已有映射完成；可在确认其输出确实不被使用后，改为仅对非空端口支撑计算。** 这是候选代码冗余，不是已测瓶颈或必然加速；有端口支撑/复数非Hermitian/恢复残差负例必须保持，收益由真实响应测量。不删除5e-13策略、1e-10原A4检查或用大常驻副本换速度。

49 outer的W5是成功基线，不为好看的步数立即换PC。短波长实际停滞或总成本明显失控时，才允许V9的唯一备选：在模态反馈内使用一次固定物理BAL_H，而非每次完整侧区FGMRES；精化次数和A6/Q/H6/映射固定，复数线性/重复及原A4检查通过后才可作线性MatMult。仅一次有界比较，以全部侧区步数、p4/模态工作与wall决定。失败不扫几十个PC，不恢复Anderson大研究，不增至上万步，不默认GPU/MPI48/node1。

## 7. 2 TB、48 h及扩大几何的资格

对象表至少含p6/p4 independent/interior/trace/port、局部类/缓存/恢复、所有真实稀疏矩阵/因子、one-cell构造、QEP正负/左右基与shift factor/workspace、packet驻留及MPI副本、DtN trace×channel、C/negative-map/LU、内外Krylov和输出。C-LU仅owner持有不代表C本体无复制。已有2 nm PEP/TOAR不再列为新迁移，补实际nev/ncv/mpd；源码默认不能冒充已测。[S6]

每次只修实测最大的超预算项，优先生命周期去重、有界批处理/流式、分布式数据，不改变物理通道/模式集合来伪装等价。完整目标不能仅按W5约43 GB乘倍率；用W2和pilot的逐项锚点校准，并给预测中央值/上界假设及差额。若目标暂不准入，选择一个有意义中间尺度，仍须交具体对象成本，不只写unknown或无望。

```math
T_{\mathrm{cold}}=T_{\mathrm{QEP}}+T_{\mathrm{setup}}+T_{\mathrm{outer,inclusive}}+T_{\mathrm{recovery/check/cleanup}},\qquad T_{\mathrm{goal}}=172800\ \mathrm{s}.
```

相邻marker的互斥阶段相加，嵌套PC与rank-max之和不再加到outer。warm复用QEP与cold成本分列，开发/失败费用另列；复用工件的历史producer资源缺测不能填0。48 h/原5 nm24 h是目标，不是新增自动强杀线；正常进展已过目标如实未达，不能归零重算。小残差不等于网格收敛，完整守恒不等于全部E/H正确。

对2 TB声明采用 `B_phys=min(实际MemTotal,2000000000000 B)`，实际2 TiB单列，整机余量至少 `max(0.2 B_phys,412316860416 B)`，case/节点/父cgroup更严限制继续有效。不把node0当全2 TB。仅因node1仍未资格不停止node0内可支付工作，但本轮不修BIOS、不使用未资格node1、不拆DIMM。

swap严格V8 observe-only：global、tree或job/cgroup非零/增长不单独拒绝、停止或判失败；记录原值/缺测，不swapoff、不清计数、不扩swap。resident减少而swap增加不能称算法内存下降；2 TB容量判断不能用换出制造假余量，应同时报告可得的同时间驻留/本job交换工作集。真实cap/floor、OOM/分配失败、磁盘、硬件错误和未关闭数学失败继续受控处理。

## 8. 数值门、停止边界与实际交付

| 检查 | 要求 |
|---|---|
| 原reported/global/bottom/top/modal | 各<=5e-9，使用原完整Hybrid A；全局小残差不能代替分块 |
| projection / traction / external-q | <=1e-8 / <=1e-8 / <=1e-10 |
| p4完整逆 | physical/augmented各<=1e-10；target5e-13、最多2次精化；全调用标量最大值而非仅last_solve |
| fixed-H6 | 原复数线性/重复/近零门；每次inner独立未缩放raw残差；逐solve标量/最大值足够，不保存全部大向量 |
| 同离散W5参考 | R/T/A/A_volume abs<=1e-8；selected复E/H<=1e-6；canonical<=1e-5；显著复幅值/功率<=1e-6；normal flux<=1e-4 |
| 能量与体吸收 | abs(A_balance−A_volume)、abs(R+T+A_volume−1)各<=1e-5 |
| 0.7相邻h/M | R/T/A/A_volume abs变化<=1e-4；selected复E/H和显著复幅值relative<=1e-3；材料侧/物理坐标/通道对应，边角奇异点单列；原更严门从严 |
| 无完整参考的W2/pilot | 离散PDE成功、物理检查、h/M资格分别分类；不得把缩减pilot称为目标规模或任意三维通过 |

正式统一 `python scripts/run_case.py <one-case.dat>`，MPI由既有公共链启动，不嵌套第二mpiexec。原生activation、complex128/IntType、MPI/BLAS等线程、source/input/physical/resolved、材料/几何/模式、artifact hash均绑定。不为网页API升级环境。代码变化在fresh进程生效，不热改已启动程序。

**首次进度提交只回答现场事实：当前runroot、runtime source、phase、是否确实运行、唯一阻塞和下一动作。** 之后开始、明确阻塞、终态及时push轻量摘要；长阶段沿现有状态至少每小时更新outer/inner、调用、残差、wall、RSS/cgroup/node0和swap。不要再让summary停在旧版本，也不要在每个数值step写巨量日志。已批准文档commit不使固定数值source失效。

新增 `response_v12.md`、一个 `outcomes/shortwave_measured_progress_v10.md`及必要compact，更新summary/test_summary/项目进度/模型总账。Response顶部列出本轮：

1. 实际完成/仍在运行的pilot阶段与场结果，或者准确的失败算子/物理量及修复证据；
2. W2真实rows/NNZ/分析/阶段驻留和下一对象额外需求，安全时继续完整解；
3. 当前最大耗时/内存对象、已实施加速或未实施原因；
4. 0.7目标模型的精度、2 TB、48 h分别处于何种状态。

P3未实施可如实记 `not_run—优先P1/P2`，不为了凑齐微基准延迟实际计算；同样不能把仅有路由测试或纯旧峰推算当P1/P2完成。真实安全阻塞可以收口受影响阶段，但必须交实际测量或可验证原因并完成其他可行项，不能虚构强制成功。

所有状态区分 `measured / derived / predicted / diagnostic / not_run / failed / controlled_stop / blocked`。保留旧负项和逐attempt费用，唯一workflow计账，旧结果派生更正可追溯。只在原分支普通commit/push，不amend/force-push/覆盖stash/删除负结果/merge master。此修订不重置执行批次、测试资格或预算；健康已运行作业保留原source/review身份，新增修订只约束后续可安全执行部分。

## 9. 审阅范围与技术依据

本次核对远端ref/任务目录、根及docs规则、工作原则、当前review/response/summary/record和相关源码；task与V9的历史合同按已读同blob复用，目录无另列补充任务书。再次检查 `test_task037c_exact_one_cell_traction.py` 的真实matched-h控制、`p4_cell_condensed_inverse.py`的请求计划与局部缩减代码。确认本次没有新的运行推送，不把新增文档当成已执行修复。

参考链接仅说明接口/机制，不证明本机已可用，安装版本与小矩阵实测优先：

- [S1 PETSc KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：右侧灵活预条件，不保证任意PC有效。
- [S2 PETSc MUMPS](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/)：外部因子、统计和每processor工作内存，不是全树RSS保证。
- [S3 PETSc MatGetInfo](https://petsc.org/release/manualpages/Mat/MatGetInfo/)：本地/全局统计与结构NNZ口径。
- [S4 Linux NUMA](https://docs.kernel.org/admin-guide/mm/numa_memory_policy.html)：可分配节点不等于整机余量。
- [S5 Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)：作业与父级限制/统计应分清。
- [S6 SLEPc PEPSetDimensions](https://slepc.upv.es/release/manualpages/PEP/PEPSetDimensions.html)：nev/ncv/mpd分别记录，TOAR已有不等于成本消失。
- [S7 PETSc MatLUFactorSymbolic](https://petsc.org/release/manualpages/Mat/MatLUFactorSymbolic/)：公开C接口的symbolic/numeric分离。
- [S8 petsc4py Mat reference](https://petsc.org/release/petsc4py/reference/petsc4py.PETSc.Mat.html)：公开文档对factorSymbolicLU/factorNumericLU标注未实现，必须核本机实际能力。
- [S9 PCFactorSetUpMatSolverType](https://petsc.org/release/manualpages/PC/PCFactorSetUpMatSolverType/)：创建factor对象以设参数，不是symbolic完成。
- [S10 PETSc PCLU source](https://petsc.org/release/src/ksp/pc/impls/factor/lu/lu.c.html)：普通PCSetUp_LU路径包含symbolic和numeric调用。

S7–S10于2026-10-08重新核阅；其余沿前版机制依据，不冒充本机新增测量。Markdown围栏/表格做静态检查；GitHub网页视觉若不可验证须明确未核验，不以此触发PDE重算。
