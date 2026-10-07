# Task041 Review V10：接受16.64 h的5 nm突破，完成真实2 nm容量试算与0.7 nm三维pilot

## 0. 审阅决定与任务身份

**无逐列Schur路线已经取得实质进展：W、5 nm、p6/h4、M480、MPI8完整consumer由旧56.15 h降至16.64 h，原五项真实残差、恢复、物理和finalizer均通过。保留其非隔离性能与研究候选边界，但不再把它描述成尚未运行或没有加速。当前主要blocker转为：新2 nm后端缺少可用于准入的逐对象内存预测，以及0.7 nm pilot仍未形成已发布的真实PDE结果。**

本轮优先取得实际场和实际容量，不再扩展独立诊断框架。保持有效的fixed-H6模态反馈＋准确p4凝聚/BAL_H侧区求解；先完成已有0.7 nm缩减pilot，并以分阶段、受监督的真实2 nm构造校准容量。两项可交换顺序，但不可并发重跑，任何一项受阻不停止另一项的安全工作。用已有代码的小范围等价优化继续减少重复工作；没有收益就保留基线，不再等待一个预测完美的PC。

```text
repository                 = Rookie1234567/MyFEniCS
working_branch             = codex/20260902-task41-mpi1-shortwave-hybrid-capacity
review_date                = 2026-10-08 (Asia/Singapore, UTC+8)
initial_audit_SHA           = b85d7a57cfb9b5d6d7d61521e199422063666c3d
reviewed_base_SHA           = 5025fdd31a1edc4ce34a8df3150a12ca90009c01
base_latest_commit         = Add opt-in matched W0.7 axial cell policy
previous_review            = review_report_v9.md
latest_response            = response_v11.md
qualified_W5_run_source    = d6fe6b2b239896e66d8c5d1bf9b8a0e45931a561
qualified_W5_invocation    = 2539de4d129f41e2ac49536bfd3b6fde
batch                      = task041_v10_measured_shortwave_progress
response_required          = response_v12.md
default_candidate          = fixed_h6_modal_gmres_research + cell_condensed p4
swap_policy                = task041_v8_swap_observe_continue
default_execution          = MPI8 x 1, frozen physical-core map, socket0/node0
ordinary_default           = unchanged
master_merge               = NOT_APPROVED
```

本轮消除“已证明的5 nm路线不能转化为短波长实测”的blocker，属于求解器性能、内存、恢复与执行治理。最终仍为**0.7 nm、目标50×25 nm单胞、约2 TB物理内存、48 h完整计算**；Hybrid内部必须满足模态传播假设，不将其等同于任意非可分三维Full3D资格。完整时间包含QEP、FE/PC构建、求解、恢复、检查和清理；warm-consumer与研发累计费用另列。

本报告覆盖V9中阻止“整场峰未知时进行任何实际容量测量”的过强解释，授权§4的有限分阶段准入；不免除下一次大分配的预算证明，不提高旧5 nm/2 nm硬cap，不放宽数学门。接受当前注册0.7 pilot及已修复的复用入口，授权必要局部修复后连续执行，不再逐项向用户索取相同授权。根AGENTS的主控/执行内部审核保留，但普通bug修复不结束整轮任务。48 h/24 h是性能目标，不是自动强杀线；不恢复swap否决，不擅自中止健康作业、重启硬件或修改运行中的代码。

## 1. 最新证据审阅与明确裁决

主要依据为本base的[Response V11](response_v11.md)、[V9 outcome](outcomes/hybrid_0p7nm_2tb_48h_v9.md)、[W5实测record](outcomes/records/task041_v9_fixed_h6_public_5nm.json)、[W2解释更正](outcomes/records/task041_v9_w2_h3_interpretation_correction_20261007.json)、[summary](outcomes/summary.md)和当前输入/代码。文件内部的早期快照与后续注册事实必须按时间和source区分。

| 对象 | 已测/派生事实 | 本轮裁决 |
|---|---|---|
| 新W5完整consumer | W、p6/h4、M480、MPI8；Schur物化列0；预付原侧区sample 0；49 outer；315次S_H含8次setup检查 | 接受fixed-H6在真实W5的完整求解，不重跑旧1920列基线 |
| 五项原残差 | global 8.573354680237858e-10；bottom 4.87285789944735e-9；top 4.3588733213657296e-10；modal 3.0159774145340474e-9；reported 8.573351523834966e-10 | 全部<=5e-9；bottom接近门限但确实通过，不为“更好看”重算，也不放宽以后门限 |
| R/T/A/A_volume | 0.7331842734229947 / 0.00022009869546076797 / 0.2665956278815445 / 0.2665962726246991；closure 6.447431546430238e-7 | 本场物理门通过；同离散复场/衍射对旧authority的独立对照应复用已存数组补齐，不用scalar代替 |
| 工作量 | 196次原侧区响应，内部步3839+3893=7732；p4回代27097、精化11633；C-LU一次factor，owner累计307/307次solve | 相比旧30296内部步约减少74.48%，约3.92倍；rank复制计数不乘MPI8 |
| 时间 | public至finalizer 59914.951233018 s=16.643 h；旧202124.563261555 s=56.146 h | 描述性时间比3.3735、降时70.36%；非隔离且方法/source不同，不声称严格隔离的单一因果提速 |
| 资源/收尾 | tree RSS 42573258752 B=42.573 GB/39.649 GiB；专属cgroup峰41376940032 B；job swap0；10项finalizer通过 | 在旧53221163008 B cap内；接纳本作业资源结果，不继承旧producer缺测项的资源PASS |
| 新W2 | packet可按原合同复用；未见新fixed-H6 FE完整结果；新后端峰仍unknown | `capacity_blocked_unqualified`不是OOM/求解失败；进入§4测量，不拿旧约650 GB直接作新后端预测 |
| 0.7 reduced pilot | 已有10×5 nm、z=-2..26、接口2/22、p6/h0.70/M400/MPI8注册输入；已做路由测试 | 可以进入真实producer/consumer；代码存在不等于packet或PDE已经产生 |
| 最新源码 | b85d7a57修复producer-root/恢复坐标；审阅中新增5025fdd31的matched axial cell策略 | 两次提交均已检查；新接口单元的离散语义须验证，不把新代码当已运行结果 |

### 1.1 两项只需离线修正的记录问题

W5 record中的`october_3_reference_comparison.current_minus_reference_T/A`与两场已列原值相减不符。按列出的数值精度，新减旧应约为：R `+3.54384e-11`、T `-2.6720737e-13`、A `-3.51712e-11`、A_volume `+1.7145e-12`。当前记录T为正5.353e-13、A为正2.658e-10，疑似混用了另一reference；不得在未核对原summary前直接覆盖。输出含两侧source/hash的派生更正，旧值保留可追溯性。这不是重新跑16 h的理由。40位Git SHA被字段命名为`source_sha256`的地方只纠正语义，不把它当64位文件hash。

早期H3 record仍称pilot `registered=false`、没有.dat，而当前tree已存在注册.dat和新路由：保留该早期record为历史快照，更新当前入口指向。材料来自归档来源的确定性候选，允许数值pilot；材料不确定度尚未传播限制实验准确性声明，不新增为pilot前置阻塞。

W5的`integrated_full3d_checker=not_available`与同离散Hybrid对照不是同一检查。先用已有10月3日完整场/600-channel数组离线比较E/H、canonical、显著复幅值与通量；缺旧资源摘要不否决数值项。真实不匹配才定位，接口/root路径错误最小修后重验已有artifact，禁止为纯checker字段重跑PDE。

## 2. 现在的性能瓶颈在哪里

旧路线预先计算4M次昂贵侧区响应；新路线不存全列Schur，使用固定近似反馈：

```math
\widetilde S_Hv=Cv-L_bJ_bH_{6,b}J_b^HG_bv-L_tJ_tH_{6,t}J_t^HG_tv.
```

H6是冻结的正定辅助近似，不是准确Maxwell逆；原LDU其余位置仍用BAL_H支持的侧区FGMRES。每次外层PC有两侧first/delta，共四次实际侧区响应。原全局A、RHS及最终物理检查未变。[S1]

**这次并非把1920次工作原封不动搬进外层：原侧区响应实测降为196次，内部步显著减少；但剩余响应更难，平均约39.45步/响应。** 新outer marker段57734.113258151 s占完整时间约96.36%；setup 2110.216175755 s，恢复59.012698122 s。57734/7732≈7.467 s仅为包含模态/正交化等成本的outer摊销指标，不能称纯内层kernel时间。

因此不再优化不存在的全列Schur构建，目标转为：减少每个昂贵侧区步的净成本、避免不必要的传递/恢复，以及在确有必要时减少外层工作。保留fixed-H6作为已成功的首选，不因它是近似PC就要求它与真实Schur逐项一致。其线性/重复门和每次实际模态inner的独立raw残差仍保留；内层自适应BAL_H不能直接伪装成固定线性MatMult。

**条件时间预算示例，不是W2预测：**若W2仍需7732个内部步，且QEP仍按旧29504.116 s计，则48 h扣QEP后，即使忽略FE/setup/模态/输出，留给内部步的摊销时间也只有约18.53 s/步。旧W2约100 s/步不能由W5的16.64 h直接消除。必须用新W2的实际N_side、N_inner、T_step与QEP分别校准，不能承诺跨波长仍是3.37倍或天然满足48 h。

## 3. 连续执行计划：结果优先，局部错误可修复后继续

| 阶段 | 最小工作与交付 | 自动继续条件 |
|---|---|---|
| P0，证据/当前作业核对 | 复用W5封存结果，纠正派生差值；查看是否已有新的pilot/QEP或健康运行 | 没有真正数学变化则不再跑13.5或旧W5；已有有效结果直接采用 |
| P1，0.7 reduced三维结果 | 沿已注册公共入口完成一个producer→validator→consumer→恢复完整场；有兼容packet则复用 | 达自身数值/资源门后先发布字段/计数/时间，不等所有精度研究结束 |
| P2，真实W2容量与求解 | 原p6/h1.5/M1200，分阶段实际构造并形成新后端内存表；通过后同生命周期进入原方程求解 | 不是先索要不存在的整场峰；下一阶段可预算且安全则连续推进 |
| P3，热点加速 | 读取7732步日志；优先验证现成route-plan/leading-PH复用，再至多一个主要净热点 | 原动作门通过且端到端有收益才采用；收益不明也不阻塞P1/P2基线实测 |
| P4，资格与扩展 | pilot的h/M相邻点、W2新成本、目标50×25 nm逐对象预测；条件合格后一个中间尺度或目标场 | 先通过相邻尺度，再扩展；不能用缩小pilot的成功代替目标单胞资格 |

P1/P2串行，按已准备的packet、容量和现有进程选择先后；P0的轻量离线工作可穿插。不因W2容量未知停止P1，不因pilot某个后处理bug停止安全的W2库存工作。对于同一代码/输入/ABI/hash已通过的节点，只测改动影响的最小范围，不重跑整个测试金字塔。

**局部bug授权：**路径、profile/CLI透传、模型注册、固定坐标、empty-owner、进程收尾、schema/账本等有明确定位的错误，保存原attempt，最小修复、实际调用链定向测试后自行继续；不因为一个新错误就整轮返回等审阅。真实数值错误也允许定位后修复并只重测受影响节点，但未修正的原算子/残差/物理错误不得绕过。同一根因连续两次仍复现，禁止第三次原样重启昂贵构造，先把定位降到最小fixture；同时推进独立的已安全工作。不同局部错误不是共享“一次失败就停止全部任务”的预算。

## 4. W2：将未知容量转为有界实测，而不是盲跑或永久blocked

### 4.1 不能混用的量

10月7日host MemAvailable约2.071 TB、node0 MemFree约854.605 GB；node0留384 GiB（412316860416 B）后约442.288 GB。这是历史两点样本，不是启动许可。host旧1.70 TiB门与node0 floor是并行约束，不是互相矛盾；新后端预测项未知才是现有缺口。保护stash `90e50393831cf8a9da6fe223ef8cae4d3cfa3976`未应用，必须核对实际工作树，不能声称其中规则已在运行。

旧642.45–647.90 GB峰来自不同后端与阶段，既不能当作当前cell-condensed新峰，也不能因取消全列Schur而认定它已经消失。应区分最终侧区p4因子、one-cell traction构造因子、临时精确PDE因子及其销毁时点；禁止把名字相似的factor记成同一对象。QEP若作为独立producer退出，则其峰与consumer峰取最大值，不同时相加。

### 4.2 本review明确授权分阶段容量准入

**允许在整场预测尚未知时，先执行可预算的几何/空间盘点、装配与symbolic analysis等阶段；这不是完整numeric factor或完整求解的无条件准入。** 复用现有runner/构造marker增加薄的阶段检查，不再建一个独立容量框架。默认保留当前W2全部物理/离散身份，p6/h1.5、M1200、MPI8、cell_condensed、fixed-H6、P4 target5e-13。若W2公共fixed-H6 guard/packet binder尚未接通，授权在已有注册边界内最薄扩展W2并测试实际argv/worker透传，不新建第二runner。输入`side_residual_correction_steps=1`与p4最多两次精化是不同语义，不相互覆盖。

执行顺序为：真实mesh/constraints与模式布局库存 → 当前所需矩阵/局部缓存形成 → 各实际MUMPS系统symbolic analysis及估计 → 第一侧numeric factor → 第二侧构造/因子 → 同时驻留与首次PC检查 → 原方程求解。每一阶段进入前，用当前驻留量、下一阶段额外对象/工作区的保守估计和释放计划证明可支付；数值factor估计必须来自当前矩阵/后端分析或经小规模校准的模型，不能只按W5全树RSS乘比例。

使用PETSc/MUMPS现有矩阵统计和原生估计接口，记录每rank rows/allocated-used NNZ、factor estimate、数值factor完成后的实际条目/可读bytes；MUMPS工作内存限制只按安装版本、每rank实际分布及非MUMPS余量设置。它不是全树cap，也不是保证RSS的魔法开关。负值、0、缺失统计须解释编码或标unknown，不能当0字节。[S2–S3]

运行时保留现有全树/专属cgroup watchdog、真实节点floor与分配失败保护；独立的硬限制是最后防线，OOM不是合格试验。若估计不可靠且无法给出下一次大分配的安全空间，只运行到已能约束的阶段，保留matrix/symbolic统计后退出；下一步优先消除已识别的重叠或重复存储。此时应交具体对象/bytes/缺口，不再只交一句`new_peak=unknown`。必要的真实单侧构造允许执行，不能以“还不知道两侧峰”否决所有单侧测量；其结果不能冒充双侧容量。

### 4.3 防止预算被重复扣减

启动时冻结本作业可用cap，至少取注册上限、规划上限、node0总容量减floor、启动node0 MemFree减floor及专属cgroup/父级限制的最严者。运行中另查node0 floor和host余量，不每次把`当前MemFree-floor`当作新的“允许总RSS”再和已有RSS比较，否则本作业已占内存被重复扣除。下一阶段应比较**新增需求**与当前余量，并同时满足冻结总cap。若记录不足以判断，先用只改变计数的fixture测试，不据此虚报现场已有double-count bug。[S4–S5]

本轮不靠降低384 GiB floor、不使用未资格node1、不清page cache或swapoff强行获得准入；不把整机2 TB当node0可用量。旧host整场准入公式继续用于无分阶段证据的完整启动；对于本节受监督的阶段式运行，以可审的阶段高水位/额外需求替代未知的整场预测项，全部非swap安全阈值仍有效。

两侧建立后，先在同一真实入射上观察前8个外层步骤/自然收敛，再观察一个restart窗口；这些是连续运行的检查点，不是强制退出重建。用已计算的残差/计数做轻量汇总；原数值、安全和进展正常则继续到完整结果。长期停滞或明显需要月级工作时，先保存可定位的实际轨迹，执行§6唯一备选/热点修正而不是提高max_it。48 h越过本身不强杀，不能归零重来。

## 5. 0.7 nm：完成已注册pilot，并让恢复与输入真正匹配

当前已存在：

```text
input/official/task041/side_balh/w0p7nm_p6h0p70_m400_mpi8_cell_condensed_pilot.dat
period = 10 x 5 nm; z = -2 .. 26 nm; interfaces = 2, 22 nm
p6 / h0.70 / M400 / MPI8
n_W = 0.9995903781323069 + i*0.00012887909720587614
selected planes = 2, 7, 12, 17, 22 nm
```

该.dat放在official目录不表示已经得到正式准确性资格；本轮把它当冻结的source-derived W材料数值pilot。保留材料原始字节、常数、单位、密度、插值区间、n/epsilon与hash；正耗散符号按当前模型。材料不确定度未量化只限制物理准确性声明，不要求先完成实验材料研究才能算这一份离散问题。

**执行一条现有公共链，不再审批一个新的wrapper项目：** fresh ABI/节点/磁盘与阶段容量 → 已有兼容producer-root则验证并复用，否则运行已注册fresh producer → producer完全退出 → packet validator/consumer payload读取 → fixed-H6 consumer → 原五残差、恢复、R/T/A/A_volume、复E/H、全部衍射与finalizer。最新b85d7a57已经实现validated-root路由；不得仅因consumer/恢复失败重算已经有效的QEP。

注册入口允许复用不代表磁盘必然有packet。先核对实际存在的manifest/shards/hash与producer终态；未存在或物理/网格/M改变才按实际需求生成新packet。不复制一个假envelope去适配目录，不重写producer source为consumer source。

**审阅中新增的5025fdd31必须纳入最终版本。** 旧精确traction路径默认`historical_local10_global100`，显式要求100 nm中段，局部精确单元长度10 nm；因此仅把接口改成2/22并不能完成缩减pilot。新commit为当前W0.7/p6h0.70/M400 pilot添加`matched_uniform_axial_cell`：中段L=20 nm、N=29，局部单元与离散传播步长均为20/29≈0.689655 nm。它改变了本pilot的接口离散定义，不是仅换目录或关闭断言；不得删除L100保护后继续使用旧10 nm局部traction。

接受这一最小方向，要求用已有定向测试核对局部矩阵的独立Schur/端点通量、正负lam/mu分解及normal/phase、单步传播与N步总传播一致、横截面primal/dual映射、selected-packet与fresh-basis构造的相同定义。至少一个真实小FE/MPI2组件oracle，不能只有mock调用参数断言；已在最终数学源码上完成且有证据的测试直接复用。首个pilot随后以原全场残差/接口连续/体吸收验证，不因此另开一个长期方法研究。

当前策略guard明确只容许h0.70、N29。后续h0.525/M600等相邻点须在每个已注册case范围内，按`L/N`和实际生成器的N派生并验证匹配策略，不能盲复用29或删除全部guard。W5/W2仍走各自原策略，不把pilot的局部长度变化静默推广过去。将strategy、local/global h、N、L及numerical_source写入数值manifest；source digest变化不能只用旧物理SHA掩盖。

b85d7a57已将`run_frozen_m10_physics()`里的参考平面/接口由旧10/110 nm硬编码改为cfg/profile值，并将BAL_H consumer profile的接口参数透传。补一组真正覆盖公共入口→profile→reconstructor/recovery的测试，确认W5仍10/110、pilot为2/22、所有采样点在本几何内、坐标和场shape来自同一配置。不可因函数名含m10就认定只支持旧几何，也不再次为这个已修复项重跑W5。保护同材料侧选择、normal、phase和体吸收积分，不只检查数组shape。

pilot当前cap为53221163008 B，保持并先做实际库存；此cap下不可支付的阶段不能开。若碰到真实容量边界，保全有效QEP/已完成结果并指出最大对象，继续W2或有界存储修复，不靠悄悄提高cap解决。资源合同更改必须显式有证据，不能把2 TB整机规格当自动提高任一case限值的授权。

通过首个pilot后，按现有建议阶梯执行相邻点：`p6/h0.70/M400 → p6/h0.525/M400 → p6/h0.525/M600`，每个为独立.dat和物理/数值身份，先检查预算再生成新QEP。前一相邻比较不足时再加一个有理由的点，不做hp×M笛卡尔扫描。不要求先证明h/M收敛才能启动首个pilot，也不能把未收敛pilot包装为准确0.7 nm结果。

完整目标几何的32056个external keys（top16030/bottom16026）与pilot的1292项是两组派生清单；必须用各自resolved输入在实际路径重新绑定、检查完整性，并保留两项nonpropagating及原Rayleigh语义。它们不是内部M。输出harmonic范围不能截掉已进入PDE的通道；只扩大report覆盖不改变边界物理。通过pilot不证明原50×25 nm单胞：同h时几何放大5倍，体量约125倍，而显式trace×channel耦合可能有更高增长，不能按一个倍率外推全部内存/时间。

## 6. 进一步加速：先复用已有低风险实现，再有条件增强反馈

### 6.1 第一优先：现成route-plan和leading-PH复用

最新W5实测记录中`route_plan_reuse=false`、`leading_ph_dual_reuse=false`，尽管这两项已有13.5 nm研究证据。先从现有196条响应日志取真实最大净热点，确认两项可覆盖的时间；使用同布局/同factor的bottom、top各一条真实非零RHS，包含一条较难方向，做原/新/新/原有界对照。

复用只能减少固定owner/索引/请求计划重建，以及一次PC内部已经算过的同一PH输入；必须保留实际值通信、ghost/周期/伴随和原A4检查。缓存不得以向量范数或旧RHS号作为相等性证明，不跨PC错误复用可变值；生命周期跟随factor/layout。原动作与完整侧区残差通过、计入setup/通信/恢复后整条响应确有收益才启用，后续P1/P2直接使用合格配置，不额外再跑一场16 h W5仅看microbenchmark。

**新增优化最多再选一项主要热点。** 优先考虑A4原残差kernel或凝聚缩减/恢复的有界编译/批处理，复用已通过的张量逻辑而非重写所有算子。按现在的全调用数统计refinement接受/失败与成本，不能因为精化多就删除`5e-13`策略或原`1e-10`检查。Math保持complex128、原积分与材料，内存不靠大常驻副本换速度。新路线下不存在全列构建热点，不继续优化旧1920列容器。

### 6.2 只有外层质量确实阻碍短波长时才启用物理反馈备选

49步W5是成功基线，不为追求更少步数立即更换它。若W2或0.7真残差停滞/总工作明显失控，沿V9唯一备选：一次固定物理BAL_H作用替代模态H6反馈，而不是内部每次再做完整侧区FGMRES。必须冻结精化次数、A6/Q/H6与映射，验证复数线性/重复；动态p4停止不能当线性MatMult。原准确侧区修正和原全局A保持。

只做一次同问题有界比较，以`总侧区步数×实测单步成本＋模态/C成本`选择，不以outer步数单独选。失败时保留实际轨迹，回到已通过主线继续其他阶段；不扫描ILU、几十个PC参数，不重开Anderson实现研究，不提高上万步上限，不默认启用GPU/MPI48/未资格node1。

## 7. 2 TB／48 h的闭合条件

### 7.1 分项模型和下一规模决策

建立一张随P1/P2实测更新的对象表，而不是一张全树比例表：p6/p4独立/内部/trace/port行、局部类/缓存/恢复、各真实稀疏矩阵与因子、QEP左右基/shift factor/workspace、mode packet驻留及MPI副本、DtN trace×channel、C/negative-map/LU、内外Krylov及output/recovery。物化C目前仍可能每rank复制，owner LU不代表C本体无复制；不得假定其对角化或删除原内部修正。

2 nm已经使用PEP/TOAR，不再列“迁移TOAR”为新加速。只补实际nev/ncv/mpd、左右与正负分支workspace和factor数据；值缺失不拿源码默认冒充。若QEP或packet成为最大问题，先优化这个实测对象：顺序/流式构造、共享只读selected数据或紧致基空间管理，每次只动一层，保留原多项式残差、选模/通量/簇子空间及packets。高阶模式数与shift因子不因TOAR自动消失。[S6]

```math
T_{\mathrm{cold}}=T_{\mathrm{QEP}}+T_{\mathrm{setup}}+T_{\mathrm{outer\ inclusive}}+T_{\mathrm{recovery/check/cleanup}},\qquad T_{\mathrm{goal}}=172800\ \mathrm{s}.
```

outer包含其侧区、模态、通信和诊断，内部拆分不能再次相加。新5nm16.64 h是warm-consumer，不是0.7 cold资格。目标原单胞仍需正式材料/输入、实际通道、h/M局部资格和以pilot/W2校准的成本模型。若模型确实不能支持目标，至少给出需要压低哪个对象/工作量、当前值/允许值/差额，不只写unknown或“无望”。选择一个最小的中间尺度校准，不无依据启动最大case。

### 7.2 安全、时间与结果分类

对2 TB声明用`B_phys=min(实测MemTotal,2,000,000,000,000 B)`；实际2 TiB另列。整机余量至少`max(0.2 B_phys,412316860416 B)`，且case/节点/父cgroup更严限制继续有效。node0仍未代表全2 TB，node1不新增为本轮前置维修任务，也不在未资格时使用它。没有测到资源项就限定声明，不虚构full-tree peak。

swap严格按V8观察：global、job/cgroup非零或增长本身不拒绝/中止/判失败；不清计数、不swapoff、不扩大swap。resident降低但job swap增加不算内存优化，不用swap兑现2 TB预算。真实cap/floor、OOM、硬件错误、磁盘不足或未关闭数学失败继续受控停止。

48 h和旧5 nm24 h仅为性能目标；已有正常进展的运行不因到点就杀掉重来。禁止未经检查把长RHS、日志稀疏或resource contract字段问题称为死锁。真正死锁/非有限/原门失败保存最小证据后修复；保留已完成QEP和安全可用恢复结果，不承诺恢复未checkpoint的p4/Krylov内存状态。

## 8. 数值资格及最小交付

| 检查 | 本轮保持的门/解释 |
|---|---|
| 原reported/global/bottom/top/modal residual | 各<=5e-9，用原完整Hybrid算子；小全局残差不能代替分块残差 |
| projection / traction / external-q | <=1e-8 / <=1e-8 / <=1e-10 |
| p4完整逆 | physical/augmented各<=1e-10；注册target5e-13、最多2次精化；全调用汇总不只last_solve |
| fixed-H6线性/重复和inner | 原复数与近零检查、实际未缩放S_H残差；逐solve标量统计/最大值，不保存全量大向量；旧scope缺测不补造 |
| 同一离散W5对已有参考 | R/T/A/A_volume abs<=1e-8；selected复E/H<=1e-6，canonical<=1e-5，显著衍射复幅值/功率<=1e-6，normal flux<=1e-4 |
| 能量/体吸收 | abs(A_balance-A_volume)与abs(R+T+A_volume-1)各<=1e-5；不是全部精度证明 |
| 0.7相邻离散资格 | R/T/A/A_volume abs变化<=1e-4；selected复E/H与显著复幅值relative<=1e-3；原更严要求从严，物理坐标/材料侧/完整通道对应，边角奇异点另列 |
| 无完整参考的2/0.7 | 原残差＋独立物理＋离散相邻证据分层；首个离散成功可报告，但不叫网格/M收敛 |

正式统一`python scripts/run_case.py <one-case.dat>`，不嵌套第二个mpiexec；生产方法在src，沿用既有service和runner。每场绑定原始dat、resolved、input/physical/source hash、环境/complex128/IntType、MPI/线程、几何、材料、模式、恢复及artifact身份；旧source与document HEAD分列。运行期间只改预先允许的文档，不热改代码；允许的文档commit不使数学source失效。

新增`response_v12.md`与一个中心`outcomes/shortwave_measured_progress_v10.md`和必要轻量record，更新summary/test_summary/项目进度/模型总账。旧负项不改写，派生更正链接原值。Git只存小证据，原始场/QEP/matrix/factor留ignored目录。

**本轮不接受仅交“路由12项通过”或再次“W2峰unknown”：**至少必须交0.7 reduced的真实producer/consumer进展及场结果或可定位失败、新W2当前后端的实际rows/NNZ/分析与阶段内存/成本、W5真实热点前后对照及目标2TB/48h缺口。条件满足后继续完整W2和pilot相邻点，不把最低交付当提前停工理由。普通工程bug可以继续修；真正无法安全进入某段时必须给下一次大分配的具体限制，并完成其他可安全工作。

开始运行、终态和明确blocker及时push轻量进度，长阶段沿现有状态至少每小时记录phase、runtime SHA、unit/PID、outer/inner/counts、残差、wall、RSS/cgroup/node0和swap。不要只推代码让用户再次无法判断是否运行。内部阶段审查不重复请求用户批准所有小步骤。

提交顺序：证据更正和最小接线回归 → 必要阶段容量/缓存窄改动及测试 → 0.7真实pilot → W2阶段/完整证据 → 相邻资格及Response V12；以实际可支付顺序串行调整。仅当前Task041分支，不amend/强推/覆盖stash/删除负结果/合并master。既有保护stash先读diff并标明所有权，只提取本review确需且审查过的窄hunk，不整包应用。此次ChatGPT只写review与执行文本，没有在工作站运行PDE。

## 9. 依据与审阅范围

仓库固定base为§0。已核对当前根/文档AGENTS、工作原则、task的历史身份和资源/失败条款、V9全文、Response V11及current outcomes/records；任务目录没有另列补充任务书。task旧MPI1/exact-only/swap等由历次review的显式覆盖继续生效，不倒改历史任务。关键代码/输入为当前`task041_balh_workflow.py`、b85d7a57及审阅期间新增5025fdd31差异与`hybrid_internal_modes.py`/`hybrid_one_cell_exact_traction_builder.py`，`physical_balanced_side_inverse.py`、已审阅的fixed-H6/LDU与p4凝聚实现、W0.7注册.dat；没有以工具接口测试代替实际数值测试。

外部依据仅解释机制，2026-10-08查阅；安装版本API/统计单位以工作站实际版本为准，不升级ABI来适配网页：

- [S1 PETSc KSPFGMRES](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)：允许非线性PC且仅右预条件，不保证任意PC迅速收敛。
- [S2 PETSc MUMPS接口](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/)：原生统计、分析/工作区和每processor内存限制；不是全树RSS承诺。
- [S3 PETSc MatGetInfo](https://petsc.org/release/manualpages/Mat/MatGetInfo/)：本地、全局最大与全局求和统计不同；结构NNZ不等于factor RSS。
- [S4 Linux NUMA内存策略](https://docs.kernel.org/admin-guide/mm/numa_memory_policy.html)：membind和cpuset限制实际可用节点，整机空闲量不能代替node0容量。
- [S5 Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)：专属作业与父级资源统计/限制；本任务swap与global不混归因。
- [S6 SLEPc PEPSetDimensions](https://slepc.upv.es/release/manualpages/PEP/PEPSetDimensions.html)：nev/ncv/mpd分别记录，已有TOAR不消除大量模式的成本。

本文数学块按GitHub fenced math，表格/围栏做静态检查；若当前工具不能验证GitHub视觉渲染，明确标未核验，不因此重跑任何PDE。
