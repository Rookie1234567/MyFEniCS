# Review V41：接受条件核心负结果，检验已知横向 Bloch 相位与低存储神经场的组合

## 0. 裁决、目标和唯一工作包

**V41 的三条真实路线及完整验收已经完成，均未求准 M5。学习隐藏层相对冻结控制的原残差只改善约 0.04547%，不能授予神经增益。停止原样加轮数、LSMR 迭代或全参数训练。本报告只批准一次物理相位引导的 FTT 对照：从神经场中显式分离已知、未折叠的入射横向 Bloch 相位，保持原方程、秩、参数规模和条件核心求解方法。**

这不是修复一个已经证实的唯一根因，也不是把旧相位试验重新命名为突破。要回答的具体问题是：不再让低秩神经核从随机初值学习已知的横向传播振荡，能否在同容量下产生有效的散射场；以及改善来自固定相位，还是还需要真实隐藏学习。相位在早期 MLP 上已有不合格结果，本次是与低存储 FTT 和已合格结构积分的有限交叉试验。

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task42extra_feinn_5nm
canonical_worktree     = /home/fenics/Projects/NN-Lab-V2
original_base_SHA      = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_result_HEAD   = 8e187eae48551812a5cd335a3c0dfbce9236239c
latest_commit_time     = 2026-10-10T14:37:48Z / 2026-10-10 22:37:48 +08:00
previous_review        = review_report_v40.md
reviewed_response      = response_v41.md
campaign               = V42_BLOCH_ENVELOPE_FTT
required_response      = response_v42.md
new_total_window_s     = 28800
review_date            = 2026-10-10 Asia/Singapore
production_merge       = NOT_APPROVED
```

最终目标仍是原尺寸 0.7 nm、任意非可分三维周期单胞、complex128 Nédélec H(curl)、双 Floquet / Fourier-DtN、完整复 E/H、衍射及体吸收；十进制 2e12 B 是整机物理内存，须保留余量，ownswap/OOC=0，单场必要准备至验收不超过 172800s。**这条神经线尚无承担该交付的合格方案。** 本批 8h 是研究上限，不是目标算例的时间成绩。

本报告仅覆盖 V41 已关闭配置的以下新研究授权。旧无相位 FTT、稠密波库及其同类续扫仍关闭。不恢复 W0/W1、模式恢复、全口面、传统 Maxwell PC、存储系统或主线接入；不修改或向 Task42、主线、dot、master 和其他工作树派活。此处 V42 是 Task42extra 的执行版本，不是隔壁 Task42 任务。

## 1. 仓库快照、已证结果及审阅范围

回读了当前分支、Response V41、summary、核心内层 CSV、条件线性算子及隐藏训练实现、根和目录规则、仓库原则；核对上一审阅发布后的 6 次提交。原 task 的未变 blob 为 a0d3606aedbbce37066338de3763fe802590dedb，与此前完整原文衔接。Review V40 从本会话原件完整读取，目录未见更新的 Review V41；历史执行补充不另开预算。未 SSH、未查看工作站实时 PID、未在审阅端复算大型原数组。下表 measured 是执行端记录，不是本端新运行。

依据：[Response V41](response_v41.md)、[summary](outcomes/summary.md)、[内层逐次记录](outcomes/records/conditional_inner_solver_v41.csv)、[完整 Gate](outcomes/records/full_numerical_gates_v41.json)、[资源](outcomes/records/resource_costs_v41.json)、[条件算子](../../src/solvers/ftt_conditional_core.py)、[隐藏训练](../../src/solvers/ftt_core_training.py)。三路线数值实现以 f0bd287e8865d9717020a1f523aaf222d24f4794 为主要 source，后续用途和保存检查另有 source；不要用文档 HEAD 替换数值 source。

| measured；M5 / 5nm / 384hex / p3 / N31968 / 40端口 | 学习隐藏 NN | 冻结隐藏 NN | Cheb 控制 |
|---|---:|---:|---:|
| 完整轮次 / 核访问 | 4 / 12 | 4 / 12 | 6 / 18 |
| LSMR 迭代 / 隐藏梯度调用 | 2887 / 54 | 2352 / 0 | 5400 / 0 |
| native 与 augmented 相对残差 | 0.938986749611 | 0.939413868293 | 0.190867855780 |
| 散射 E 相对误差 | 0.999900336902 | 0.999911279035 | 0.990621722409 |
| 散射 H / scaled-curl 相对误差 | 0.999917056728 | 0.999927758525 | 0.990550679422 |
| 独立能量闭合误差 | 0.416324447019 | 0.416298949011 | 0.411709886126 |
| 实际网络重建相对差 | 4.61e-14 | 5.40e-14 | 1.04e-14 |
| 正式 attempt 秒 | 1371.57181736 | 1514.96984082 | 3384.24254840 |
| 同时树 RSS 采样峰 / B | 469508096 | 393895936 | 388096000 |
| 结束原因 | BLOCK_ALTERNATION_STAGNATION | BLOCK_ALTERNATION_STAGNATION | ROUND_LIMIT |

模型重建、MPC、端口及求积 PASS 不抵消原方程和完整场 FAIL；所有 R/T/A 仍仅 diagnostic。LSMR 有停止码 2 和 7，独立伴随残差已报告，但它们不证明每个条件问题达到精确最小值，更不证明全部三核联合最优。不能仅将 maxiter 从300放大便承诺求解。

V41 的权限用途字段与恢复目录错误已同批修复，健康 producer 未重跑；本轮保留修复，不再用 writer/渲染问题解释约100%的场误差。V39 的64/78倍只是映射完整工作加速，不是超过传统 FEM 的同精度收益。

## 2. 唯一表示改变：提取横向相位，不改变原 Maxwell 方程

### 2.1 数学与物理身份

对本仓库 exp(-i omega t)、空间 exp(+i k·x) 约定，取实际 cfg 中**未经倒格矢折叠**的入射横向波矢 k_parallel=(kx,ky,0)，定义：

```math
\chi(x,y)=\exp\{i[k_x(x-x_c)+k_y(y-y_c)]\},\qquad
E_{\theta,s}^{\rm scat}(x,y,z)=\chi(x,y)F_{x,s}(x)F_{y,s}(y)F_{z,s}(z).
```

x_c/y_c 为原盒中心；phase_z=0，不引入入射 kz、衰减参数或多载波。乘积可等价写为三个核，其中 x/y 核分别乘各自一维相位，z 核不变；连续场 TT 秩及9072/9120个可训练实参数不增加。常数包络可以直接携带已知横向平面波，这是待检验的结构优势；不是已证明整个散射包络平滑、低秩或可被正确训练。

原M5参考值 kx=1.2564456695248023 nm^-1、ky=0、Lx=10nm。由此推导 kx Lx 约12.56446 rad，即约1.9997个周期。虽然周期缝相位接近1，胞内并非几乎不振荡。**不能对 kx 做 mod(2pi/Lx) 或折叠到第一 Brillouin 区后再用作本载波。** 数值必须从原运行配置回读，不从近似文字回填。参考旧[相位定义](outcomes/phase_representation_plan_v7.md)，冻结新 phase_definition/hash。

该选择来自入射，不来自准确场、残差频谱拟合、POD或teacher。全部衍射项仍保留：提取共同 k_parallel 并没有删除其余倒格矢谐波、倏逝场或材料界面变化。

```math
c_\theta=I_h^{\rm curl}(\chi F_xF_yF_z),\quad
r=A c_\theta-f,\quad L=\frac{r^*r}{2f^*f}.
```

原A/f、原背景及FE基不变；不另组包络方程，不漏掉 curl(chi u) 的相位贡献，也不以包络残差替代实际FE残差。实际H仍由最终完整FE场的curl恢复。相位必须在物理积分点、完整矩和Piola之前施加；不能给FE系数乘中心相位。原MPC仍只展开一次，不能再给已恢复slave追加相位；也不假定有限网络包络天然满足周期。

单位模相位**不改善一维特征Gram的条件数本身**；它主要改变特征与所需振荡场的匹配。V40近相关性和原方程病态性仍可能导致失败，不能将本变化称为已经解决二者。

### 2.2 不是首次尝试相位思想

[V8结果](response_v8.md)已显示旧相位MLP的散射E误差约21.35%，好于plain约99.89%，但原残差1.3193且联合FAIL；后续相关负结果不撤销。当前试验的区别是：低存储三核FTT、已合格的一维积分收缩、条件核心LSMR和隐藏学习消融；仅取横向共同相位，不是原三维入射载波MLP的原样续跑。它是有限交叉试验，不是原创性或成功保证。

外部依据仅作机制背景：[PhaseDNN论文](https://arxiv.org/abs/1909.11759)、[FTTNN v1](https://arxiv.org/html/2510.13386v1)。未搬用标量Helmholtz、可分积分或GPU实验的收敛/成本结论；本案材料始终保持非可分原分布。

## 3. A：把相位接通全链路，一次完成资格

采用最小 opt-in envelope/schema 适配，不复制新的FTT/监督/调度系统。默认无相位路径不改；phase向量、原点、单位、符号、模式身份进入buffer和manifest，缓存key覆盖相位。仅新增非训练buffer，初始化仍用seed4213701、原Xavier/Cheb规则、x/y非零、z输出零。两条NN初始实参数逐位相同，散射c0严格零。

明确风险：`ConditionalCoreAction.K`及`DirectionField`当前用axis_features替换活动core，可能绕过只加在model.core里的相位。必须把同一物理相位完整地传过活动增量、K/K*、B/B*、完整VJP、隐藏梯度、准确逐点后备和独立export；不能只改forward。反向是相位的共轭乘法。禁止模型与导数同时漏相位、然后靠自洽dot-test宣称正确。

| 必需资格 | 标准 |
|---|---|
| phase=0 回归 | 新/旧非零模型c、原loss、VJP、K/K*及一次更新相对差≤1e-10 |
| 独立物理相位 | 单独点值chi乘未改FTT输出，与新逐点/张量路径配对≤1e-10；全部边/面/内部矩、真实J、方向与owner |
| 周期与符号负控 | x/y两个非单位相位的合成见证及角点；实际M5 ky=0另列；错号、归一化坐标误用、折叠kx、重复MPC须被检出 |
| 核心与隐藏导数 | 纯虚/bias/三分量/三轴K线性与复伴随≤1e-10；至少三个非零隐藏FD方向稳定区≤1e-5 |
| 积分及恢复 | q30/q60完整c及原A作用≤1e-8；缓存相位/参数失效、接受/拒绝、完整恢复一致；产物用途false端到端核验 |

使用零相位、解析常数复包络及一般非零FTT作测试；解析场只检实现，不能当M5 PDE通过或候选warm start。先小模型与原packet见证，不重跑V40容量谱、旧oracle、旧完整benchmark和准确参考。

保留已合格FactoredMomentMap的一维有限和重排，chi可直接乘轴核积分。若某几何/矩不支持则走原准确后备，不降q、删小非零或把真实J清零。若q配对失败，先修单位/符号/布局和数值稳定性；不根据拟合结果随意加q或降低门限。相位实现不能以性能为由漏掉高阶矩。

每模型最多三次完整工作计时，含核求解所需K/K*、原A/A*、更新后c/r与存盘；只确定成本与资源，不做长benchmark。所需修复属于本批，不在资格PASS或commit处分段等review。

## 4. B：三条从零对照，允许同批数值分流

| 路线 | 相位 | 核心求解 | 隐藏函数 |
|---|---|---|---|
| BLOCH_FTTNN_CORE_LEARNED | 同一固定chi | V41条件LSMR | 每轮真实学习 |
| BLOCH_FTTNN_CORE_FROZEN | 同一固定chi | 完全相同 | 初始隐藏固定 |
| BLOCH_CHEBTT_CORE_CONTROL | 同一固定chi | 同一框架 | 固定Cheb T0..T18 |

共同原M5/5nm/384hex/h1.25nm/p3/N31968/40端口、rank8、9072/9120实参数、native-EUC、体/DtN q15、网络q30不改。神经两路线同一初值；Cheb用原强控制初始化，不人为弱化。V41无相位结果作历史对照，不重跑第四条，也不声称历史比较严格同时硬件隔离。V41终态、旧phaseMLP、监督fit、V40参考矩一律不作为初值。

核心仍是B=A K/||f||、b=(f-Ac)/||f||上的增量LSMR：damp0、atol/btol1e-8、conlim1e12、maxiter300，增量零初值；仅神经核系数空间求解，不允许全FE完成器、A/G因子、Gram逆、A*A、显式N×d矩阵或新PC。每次实际写回网络并复算c/r，线性性≤1e-10、原loss不增才提交；线搜索/返回码不代替原方程。

首轮z→x→y，下轮反向；每条最多6轮/18核访问/5400 LSMR迭代/5400s，任一先到。只有LEARNED每轮更新全部912个隐藏实参数，固定输出系数，沿V41 fresh L-BFGS配置：lr1/history10/strong-Wolfe/max_iter10、实际调用≤20。不称其为精确VarPro reduced gradient。

保留V41原停滞条件：前两轮后，连续两完整轮次的原残差改善均不足1e-3且原残差>1e-2，则结束该候选并验收。另加入两个可证伪检查点，避免再次仅靠loss耗完预算：第2轮后若native>0.5且散射E和H误差均>0.5，记EARLY_NO_FIELD_PROGRESS；第4轮后，只有三项均≤0.1，或最近两轮native至少减半且E/H均≤0.2，才继续最后两轮。这些只是研究分流，不是正式精度门。

检查点由隔离checker只返回规定的标量/布尔值，不回传参考向量、误差图或通道方向；标记validation_used_for_stopping=true、benchmark_previously_seen=true、design_informed_by_reference_diagnostics=true，不冒称盲测。一个候选失败不取消其余路线及完整验收。工程bug同批修复，不把数值停滞伪装成bug重置预算。

## 5. C：完整数值、用途与投入裁决

每条final committed从磁盘重开，独立路径用保留的原逐点FTT输出再显式乘chi，原完整矩q30/q60及FE compare-only核验。不得只让新core方法与自己比较。原参考仍为V1同p3，SHA256 0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7，不重求MUMPS。

| 联合 Gate | 不变阈值 |
|---|---:|
| native、augmented、独立total原方程 | 各≤1e-6 |
| total/scattered E/H/curl、六点复场、四类完整40复通道向量 | 各≤1e-4 |
| R/T/A/A_volume、体吸收一致性与独立能量闭合 | ≤1e-5 |
| 逐衍射级功率差 | ≤1e-6 |
| 实际模型重建、MPC、端口恢复 | ≤1e-10 |
| 网络完整矩/原作用、FE积分独立求积 | ≤1e-8 |

实际模型和producer分别评分；保持原完整分子/分母和近零规则，不拟合整体相位，H来自实际E的curl。原残差失败时所有功率仅diagnostic。raw/manifest/checkpoint/compare/seal/reopen/最终checker全链production_initialization_allowed=false；保留V41原错误及修复，不能只改README标签。

只有满足同一严格精度后，才能比较时间或同时峰≥20%的资源收益；还须区分相位本身、条件线性算法与隐藏学习。仅frozen或Cheb通过不是NN成功。研究强信号另外要求native/augmented≤1e-3且散射E/H/curl各≤1e-3，不授production。

本批不自动开监督fit、oracle、容量证明、多个载波或初始化/优化器扫描。若仍只得到几个百分点的残差改善、场仍严重不准，关闭本相位配置，不直接再发同族变体。没有严格或强数值信号，结论保持NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE；不把小内存或实质代码改动包装成目标进展。

## 6. 条件0.7nm与目标资源

仅LEARNED先通过M5全门、两控制已冻结并验收、现场资源安全且总窗余时≥7200s，允许一个M5全部几何长度×0.14的真实0.7nm非可分三维pilot。使用统一材料表的正式0.7nm条目，重绑定实际模式、背景、网格和参考；新chi从新cfg.kx/ky计算，不硬套40模式、不直接缩放旧FE系数。可用合格无标签M5模型的归一化核参数作初值并计其前缀成本。训练最多2轮/1800s，剩余优先完整验收；未准入不注册空输入。

该缩放保持近似几何/波长比，至多验证材料和小型三维链，不能证明原50×25×140nm目标、任意复杂场低秩、p/h或端口收敛。乘一个相位也不会免除网格分辨率要求。2TB会放宽资源，但不会消除剩余倒格矢振荡、O(N)全场/残差、原算子/CL展开和DtN存储；目标还需要准确离散及多个电尺寸全过程容量/时间模型。

新候选从零开始，V41失败训练不是其部署必须前缀，保留在研发历史账；真实必需的网格/native/moments准备不能免费。分别报告loaded-packet实测、冷N=1缺项、历史研发和条件迁移成本。冷N=1未测完整就UNKNOWN；不得将0.618s内核历史成绩当作本轮端到端承诺。

## 7. 同批修复、资源和Git

新唯一总窗28800s，从首次实际准备计入实现、失败、等待、正式数值、保存、验收和发布；不与V41剩余时间叠加。A软7200s，B每条硬5400s，C/发布优先保留至少1800s；未用软预算可登记转移，不扩大单条上限。已有合法V42作业先识别继续，不因重复消息重开窗。

保持CPU-only/MPI1/math/Torch1、一个现场合格物理核、numeric warn12/hard16GiB、含临时规划12GiB、新cache/AD≤1GiB、轻2GiB、ownswap/OOC0；原PSI/CPU/SMT、系统max128GiB或10%及384GiB邻增长保护不变。成功60s准入计总wall，真正拒绝后额外前台等待≤900s，不沿用耗尽的旧观察池，也不放宽阈值。

普通API/schema/相位/共轭/导数/缓存/角色/保存/用途问题：定位→最小修复→受影响targeted测试→完整健康边界继续，无普通bug次数交棒卡。数学更改另commit并标明受影响证据；日志/渲染/封存错误不重跑健康producer。每核心/隐藏边界原子保存全部模型/phase buffer、位置、c/r、RNG和成本；未保存的LSMR双对角化不能冒称可恢复，丢失工作照计。150s收口、至少120s保存；不依赖SIGKILL的finally。

先只读branch/HEAD/worktree/锁/PID；合法运行中不改源码或HEAD、不kill、不启动副本。安全同步只用精确refspec；不reset/stash覆盖、不amend/强推、不merge master。同分支纯review与本地未推送实现分歧时仅沿既有执行补充的受限普通merge规则保留双方历史。

## 8. 输入、证据和停止交棒

新数值逻辑进src，复用现有runner、durable和FE检查流程；先实现/validate、定向测试和clean实现commit，再按依赖串行运行：

```text
input/task042extra_feinn_5nm/v42_bloch_ftt_checks.dat
input/task042extra_feinn_5nm/v42_bloch_fttnn_learned.dat
input/task042extra_feinn_5nm/v42_bloch_fttnn_frozen.dat
input/task042extra_feinn_5nm/v42_bloch_chebtt_control.dat
input/task042extra_feinn_5nm/v42_bloch_independent_compare.dat
```

```bash
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/<one-run>.dat
```

wrapper选择正确FE/ML/pure activation并调用scripts/run_case.py，逐项清场。正式run绑定input_original.dat、resolved_config.json、run_manifest.json、input/physical/source SHA、run_summary.json、环境、MPI/线程、资源及artifact hash。条件0.7nm输入只在真实准入后建立。

交response_v42.md、outcomes/bloch_envelope_ftt_v42.md，及compact相位定义/负控/导数、内层与隐藏更新、标量分流、完整场/通道/功率、资源/修复/用途及run索引；大数组留ignored。更新本分支README/summary、progress/模型总账/tests/changed_files，历史保留，不full pytest、不重装、不全仓反复hash或重渲染。

**不要在接口、commit、第一次bug或一条路线失败时交棒。** 完成三路线及独立验收，或触发真实安全/数据/总预算硬出口后一次交付。明确科学负结果也属于有界包的完成，不保证PASS。报告完整HEAD、显式tracking/ahead-behind、clean和自身清场，只推本分支。不把本批变成长期无人监管循环。

本审阅端仅作小型相位/复伴随代数和文档检查，不替代M5。GitHub完整视觉如未取得则NOT_VERIFIED，有限补查关键页即可，不因网页错误阻断数值。最终必须回答：提取已知横向振荡后，场是否真正改善；隐藏学习是否优于同相位冻结/固定核控制；联合数值和同精度成本是否通过；原尺寸0.7nm还缺哪些证据。
