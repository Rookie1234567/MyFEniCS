# Review V74：关闭残差近1的重型组合，先用廉价对照与残差最小化决定是否继续

## 0. 决策、责任与唯一身份

**V75是执行完成、数值失败，不是有效求解进展。原残差0.999209813227，256步仅降低0.0790%；不批准harmonic+38RAS尾部、另建粗空间、继续提高restart或扩大资源。此前ChatGPT在缺少最简单同题对照、未验证修正组合效力的情况下，连续授权重型准备和固定256步，决策证据不足。本轮改变准入规则：先取得便宜而真实的基线，只给一个不建新矩阵的三方向残差最小化候选有限机会；显著降低原残差才允许继续，失败立即止损。**

要消除的blocker：当前正确算子与局部因子不能形成有效的全局修正；缺少PCNONE/Jacobi同题对照，且固定粗/局部相加可能把有效方向绑成差方向。后一项是可检验假设，不是已证唯一根因。本批不再用组件PASS、低RSS或文件数量代替有效解。

```text
repository       = Rookie1234567/MyFEniCS
branch           = task42_neural_coarse_inverse
worktree         = /home/fenics/Projects/NN-Lab
original_base    = ccd357885f7f9be84efe3be07868cc94f13d93fc
reviewed_HEAD    = 977616bf4fab280fb0e2ba9c9d9bc8dfaf650ce5
result_time      = 2026-10-12T02:29:23Z / 2026-10-12 10:29:23 +08:00
science_source   = 6009967437ed5853ddd9f5f71780f3cf00c32bbd
previous_review  = review_report_v73.md @ 02703c5ce56a18b134b50eded39645cb422a0d95
campaign         = V76_CONTROLLED_BASELINES_AND_RESIDUAL_MINIMIZATION
response         = response_v76.md
ordinary_default = UNCHANGED
merge            = NOT_APPROVED
```

目标不变：原尺寸50×25nm周期单胞、z=-10..130nm、0.7nm、任意非可分三维材料/几何、complex128 Nedelec H(curl)、x/y Floquet、z Fourier-DtN；十进制2e12B为整机物理内存且留系统余量，ownswap/OOC=0；必要构建至完整验收≤172800s。当前s=7/135、MPI1是有限方法实验，不能代替目标资格。NN仍由邻支研究，本批不训练NN、不做teacher、不复制Task40 reference-q或Task42extra任务。

本合同明确覆盖旧“不跑廉价基线”“不得改变PC组合”“没有早筛选”“失败也必须重复完整昂贵场输出”等与本文冲突的阶段限制；不改物理、最终精度门或资源安全门。旧失败和旧时钟不改。用户本轮要求节约时间与token，禁止本批再扩写历史流水账或重建已关闭的研究前缀。

## 1. 审查证据与不能混淆的结论

已读V75 response、summary当前段、factor/PC记录、上次review后的6提交增量、原作用/PC/FGMRES调用链；回读根规则，原task、docs规则、仓库原则和无独立supplement的目录事实沿本会话已读全文及未变增量衔接。完整阅读挂载的Review V73。没有声称逐行重审全仓、SSH核查当前进程或重新运行大数组/PDE。

主要证据：[R1](response_v75.md)、[R2](outcomes/records/factor_inventory_v75.json)、[R3](response_v73.md)、[R4](outcomes/summary.md)、[R5](../../src/solvers/bounded_trace_pc.py)、[R6](../../src/solvers/bounded_trace_study.py)、[R7](../../src/solvers/physical_retained_fgmres.py)。代码与结果判断固定于reviewed_HEAD。

| 执行机记录，不是审阅端实测 | V75实际值 | 裁决 |
|---|---:|---|
| full FE / retained+port | 1943745 / 1177293 | 同一25576tet/p5/828 |
| KSP / 实际步数 | 1 / 256 | 已完整检验，不因bug截断 |
| 原true / retained true | 0.999209813227 / 0.998989109972 | 远超1e-6 / 1e-11 |
| 128步原true | 0.999210629605 | 其后128步几乎无收益 |
| harmonic粗修正单独作用于物理RHS | 残差比1.43201287668 | Galerkin正确不代表残差收缩 |
| total E误差 / V70范数 | 0.997988393182 | 不是仅由小分母制造的失败 |
| sampled整树峰 | 44.0530548096GiB | 失败候选的内存，不是同精度收益 |
| 健康组件 | 960宏、完整Galerkin/对偶、快速原作用和恢复 | 可保留，不称有效PC |

V73同物理RHS上，旧p2粗修正单独后的scaled retained残差比为0.487639686028；固定接上局部修正后为60.7130442268；平衡组合为77.9655797366。[R3] 这不能证明局部算子有实现错误，也不要求所有PC都是收缩映射；但说明“正确修正相加必有效”不成立。之前没有先做简单同题对照，就继续更换粗基，不合理。

还应更正理论定位：Li–Hu的Maxwell-harmonic研究包含阻抗局部子问题、谱选择或其特定经济变体及稳定性条件；固定p2骨架Dirichlet延拓加当前主子块RAS不是其已证明鲁棒的算法。局部齐次、Galerkin或复对偶PASS均不能搬运波数无关收敛结论。[T1] 同样，任何新小残差组合都不能宣称已获得通用Maxwell粗空间。

## 2. 冻结对象与禁止的新投入

只读复用V70精确local_packet、q47/q63、原RHS与尺度，V71的38块CSR、原多项式Z0和E0。**不使用V75的新harmonic基作为本批候选的必需组成，不继续其准备；旧Z0/E0只作为现成修正方向使用，不恢复旧固定求和算法。** 不读取global fine K/S或全局fine因子，不重建38块/粗矩阵，不增加粗列，不重解直接法参照。

```text
mesh_sha256     = c470274ab6c64cee0b8eef09dbcdadadfac4c6ca229d7fc2b6e608ded62f540c
material_sha256 = 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2
physical_sha256 = df26b8cf28e1115bdb2eb9ac9b79e698596133305310d26c1d664f94e2c5be44
packet_sha256   = 9bef5add6398999c70c21c7f26a86833fc1eb46f98598c8503aa3c41743728da
Z0_sha256       = 536758160a20d38c5fc87781a192fd853d6f387164774181c12595d0daa3880e
```

实际路径、E0、RHS、left/right及数组成员hash从健康manifest解析，核对原坐标，不混用文件hash和裸数组hash。细层仍含原767280个内部自由度，全部恢复；材料/入射/κ/828模式/边界积分不变。不得用V70正确场构造初值、RHS、修正或选权。

## 3. 先补廉价基线：两次32步，不建大型PC

B0：同一scaled retained系统、RIGHT FGMRES、PCNONE（或完全等价identity callback），物理retained零初值，restart128、max32。

BJ：同配置，仅使用真实复对角Jacobi。对角由local_packet逐单元贡献及实际端口块累加；对非一对一MPC展开，必须计算diag(E_e^H S_e E_e)，不能仅累加原cell对角。行列尺度各一次。精确零对角对应逆值1并列出数量，非有限或数值溢出记BJ不可用；不扫描移位、阻尼或阈值。保存对角及固定向量作用。可用无需global S的分量核对；不为一个对角重组全局矩阵。

两项都在0/16/32步记录scaled explicit retained，0/32步及任何候选通过处检查完整独立原方程和端口。记录operator次数、KSP时间、准备与审核成本；固定32步结果不是合格解。二者都用相同原正交化/norm、相同尺度和同一RHS，另按全域原作用数与wall比较，不能只按outer步比较更昂贵的候选。

若任一基线32步已联合通过，先保存并完成唯一完整输出，不再启动SMR。若有基线满足第5节明显进展门，允许最多一条基线从本批32步状态延续；先保存两项对照，再按较小原true选择，误差差距≤1%时选择累计wall较短者。该选择只用当前RHS残差/费用、不用V70场。新KSP会失去原Arnoldi基，必须标注续算而非原进程连续；最大步数仍按该路线累计256计。若该延续成功，取消SMR；若停在效果门且总预算足，SMR仍只有下述一次机会。

若两项都没有明显进展，不扩成参数扫描，进入SMR。B0或BJ接线错误只影响对应项，合法原作用与另一路继续。累计简单基线准备及32步对照预算1800s；不是宣布它们会收敛，也不能以没有理论保证为由不实际运行。

## 4. 唯一候选SMR：不再把粗与局部修正固定绑成一个方向

### 4.1 数学和依据

设A为原scaled retained算子，C0=Z0 E0^{-1} Z0^H，B为已保存38块RAS。对PC当前输入v，仅构造三个候选方向：

```math
d_0=v,\qquad d_c=C_0v,\qquad d_l=B(v-A d_c),\qquad
D=[d_0\ d_c\ d_l],\quad W=AD.
```

不再无条件返回d_c+d_l，而用同一原算子的真实作用决定三项权重：

```math
a_* = \operatorname*{argmin}_{a\in\mathbb C^3}\|v-Wa\|_2,
\qquad P_{\rm SMR}(v)=Da_*.
```

它只解3个复数系数的小最小二乘问题；不训练网络、不增加FE未知量、不建新局部或粗矩阵。身份方向d0使最小方案也能使用普通原残差方向；它不保证外层整个搜索空间包含PCNONE的完整Krylov空间。

在精确算术且保留候选空间时，直接有：

```math
\|v-A P_{\rm SMR}(v)\|_2
\le \min\{\|v\|_2,\|v-A d_c\|_2,
\|v-A(d_c+d_l)\|_2,
\min_{\beta\in\mathbb C}\|v-\beta A d_0\|_2\}.
```

这是本轮具体可验证的改进，而不是仅更换算法名称。若原物理RHS、C0及坐标完全同V73，首次PC输入上的界应包含约0.48764的旧粗修正；FGMRES第一步还会在返回方向上最小化。因此**第一步scaled retained最小残差不能再被迫接受旧固定和的坏方向**。该界不直接保证未凝聚原残差同幅下降，也不保证后续收敛速度；两者必须实测。

本方法是小型残差最小化非线性PC，不是论文完整MPGMRES实现，不复用其整体最优性结论。多修正方向与最小残差的思想有原始研究[T2]；FGMRES可接受非线性右PC[T3]。没有新波动信息时它仍会停滞，这正是本轮有界判别的出口。

### 4.2 数值实现与实际成本

复用BoundedTwoLevelPC.coarse_apply/local_apply与原HotTracePacket，不调用旧固定__call__。只分解原38局部块+旧E0；不分解新E_H。每次PC需A d_c、A d_l、A d0，必要的返回向量检查另计；不能把这些隐藏为外层一次作用。局部因子三角求解仍昂贵，SMR每步不预告更快。

直接对N×3的W做稳定QR或SVD，小列归一化必须对D同步。禁止通过W^H W平方条件数；允许固定rcond=1e-12仅识别这3个候选方向的数值相关性，不删除PDE未知量。每次保存三列范数、小R/奇异值、秩、权重、预测残差和选择结果；不保存每步全部大W/D。额外工作区≤512MiB，N约117万时几条向量可放入，不得成长为长期列库。

为保持上式的数值保护，显式比较小LS解、零步、单独最优缩放d0/dc/dl、原固定和五类可行结果，采用真实线性组合残差最小且有限的一项；退化/秩判定不能把更好的单列候选丢掉。非零返回用一次真实A z复查，差异超过1e-10运算尺度时做一次较稳定的小QR重算或回退已验单列；持续不一致视为实现失败。这个额外作用照计。

零输入精确返回零。不要求P(v+w)=P(v)+P(w)：它一般非线性，旧“linear_operator_frozen=true”及加法线性Gate不得误套。验证有限性、复数齐次/退化兼容和真实残差保护。权重不依赖V70或历史正确解。

### 4.3 接入一个真实求解，不另写Krylov软件

复用physical_retained_fgmres，RIGHT/restart128、最多256步、原norm/正交化。零初值。记录第1步原式及接口残差，随后16/32/64/128和终态；原式身份门不降。不使用“内层3维loss”代替原残差。

Q只需要一个非Hermitian小代数例、两个真实当前输入（物理b及首个Arnoldi输入可共用）、旧作用接口配对。若首次显式scaled retained仍接近1而上式对应旧粗方向约0.488，先检查first-step/buildSolution/PC桥接、列复共轭和数据身份；不能再跑256步掩盖这一可定位矛盾。若C0旧资产不可恢复，SMR记ASSET_BLOCKED，不重建约一小时Galerkin，廉价基线仍可完成。

## 5. 效果与时间门：从“默认跑满”改为“有用才续”

下列是项目投资/时间门，不是数学收敛定理。定义rho=max(未凝聚原true, scaled retained true)，均除各自原RHS范数；不能重设归一化为上个restart残差。

| 路线累计步数 | 继续的最低效果 | 未满足时 |
|---|---|---|
| 32 | rho≤0.5 | 保存完整系数及原式，效果停止；不补尾部 |
| 64 | rho≤0.1 | 同上 |
| 128 | rho≤1e-3 | 同上 |
| 256或时间/调用上限 | 以最终联合门判断 | 不自动扩大restart、步数或改PC |

每步下降不是必要条件；门仅在上述预登记点判定。SMR在32步即便勉强过门，若取得同残差所用wall和全域作用显著劣于合格廉价基线，优先已批准的基线续算，不为了新方法标签继续。上述停止只能判定该配置未满足当前成本目标，不宣称数学上永不收敛。

本批最多4次KSP调用：B0、BJ、一次选定基线续算、SMR各至多一次，普通重试也占总额。每条物理路线累计≤256步；总全域fine作用≤1800，含PC内作用、显式true和独立全域审核；KSP累计有载≤3h。没有表现良好的路线，就不再把剩余时间用于新谱/波库/impedance开发，关闭本组固定机制。

## 6. 成功与失败的不同交付，避免反复昂贵输出坏场

正式门不变：retained≤1e-11；独立原true/native/augmented/port各≤1e-6；恢复/MPC/Schur-original≤1e-10；direct目标1e-10另列。候选联合通过后，必须恢复全部FE、六场、原240点、828物理复通道及逐mode功率、R/T/A和独立体吸收/能量；以V70严格同离散比较：六场/点/复通道≤1e-6，RTA/Av差≤1e-8，逐mode差≤1e-9，能量≤1e-5。同一差分分子、两固定分母，不校幅相、不投影、不删通道。

**原残差仍大于1e-2的失败候选，本批不再支付数十分钟做整套体积分、衍射评分和无价值的诊断图。** 保存完整retained、RHS、尺度、source、恢复包、完整恢复系数与独立原式向量，足以之后只读补消费；official=False，昂贵物理输出明确NOT_RUN_BY_FAIL_FAST_POLICY。最多对一份已联合通过的最佳候选做完整昂贵验收；若无通过而有≤1e-2的最佳候选，按余量最多做一份诊断输出，不冒充合格解。该条显式覆盖旧“每个明显失败场都全输出”合同。

释放KSP/PC/局部和粗因子并记录RSS后再恢复/输出。writer、JSON、图表或collector错误只补消费，不重新分解。保留最终调用次数、全部失败费用，prepared-start不是从几何开始的冷N1；父准备不免费。未达到同精度，禁止授生产速度或内存改善百分比。

## 7. 资源、普通bug和任务组织

新总窗6h，从本轮第一项实际工作开始，所有适配、等待、失败、读盘、求解与验收计费；至少4500s留给可能成功场的完整验收，最后1800s只收口。不是6h成功承诺。实现/定点回归预算≤3600s，其中修复累计≤1800s；不得刷新窗口。若简单控件适配已耗尽预算，不新起框架，交付现有基线与真实阻塞。

默认无大因子角色64/80/96GiB；仅SMR与需要旧局部因子的角色96/112/128GiB；因子双倍symbolic总≤80GiB。每个因子前live RSS+尚未分解双倍symbolic+future≤96GiB，future≥12GiB且包含长Krylov库/小LS向量。零OOM探测，原complex128/int64、MPI1/math1/CPU1/GPU0、ownswap/OOC=0、PSI/cgroup/宿主/384GiB邻增长/CPU-SMT及机器heavy锁不变。2TB绝非自动准入票。

不准新global fine K/S或fine LU；只读父local_packet、旧38块和旧7068阶E0。已有因子不能声称已序列化；SMR独立进程需要实际39个numeric并计费。不为了共享因子新建常驻服务。新ignored上限16GiB、Task上限仍696GiB、free≥50GiB，完整成功输出前核对原子双份空间。

使用参数化scope/strategy接通新role，不用旧版本字符串名单隐式回退。廉价基线不得无条件调用numeric_factors。小LS-PC不能经过旧线性加法资格；控制向量属于本批RHS，不是teacher。候选冻结和全批冻结分离，不能在B0结束时把后续路线锁死；动作计数贯通所有层，不能遗留600门。raw计数/残差随计算落盘，不等最终report。

普通局部bug：定位→最小修复→相关targeted回归→续用健康资产；同根因两次失败不第三次盲重放。原式、ABI、材料、身份和监督不可信先隔离。测试仅覆盖对角/MPC、3列复数LS、退化保护、非线性PC、效果门与分流；不full pytest/CI、不全仓扫描、不重跑FLAT/15表/慢oracle/旧完整解。文档只做一次紧凑检查；两总账新增一个有结论的短条目，不复制历史。

## 8. 入口、提交与路线出口

待创建入口，每dat一项明确计算：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v76_minimal_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v76_identity_control.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v76_jacobi_control.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v76_residual_minimized_solve.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v76_promoted_control_continue.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v76_verify_cost.dat
```

实际执行按第3节分流，不能照顺序盲跑所有dat。实现先commit clean，资格化activation、targeted回归、compile/Ruff和dat validate后运行。PRECHECK/VERIFY不暗藏KSP；优先复用原作用、恢复、原式与输出，仅新增小型PC策略、简单baseline和效果门。

提交计划：C1最小策略/基线/效果门与定点测试；C2实际执行及紧凑证据；C3最终response与两总账。活跃数值期间不改tracked source/HEAD。仅本分支push，不merge、不操作邻worktree、不改系统或邻任务、不自动V77。

交付response_v76.md、outcomes/baseline_residual_minimization_v76.md与紧凑records：同题B0/BJ控制、实际每个方向作用与3列保护、完整残差/成本/调用/峰、停止原因、是否有合格场。报告“哪种配置被否决”而不是“哪几个测试通过”。读最新Task40工程ref及Task42extra仅作范围登记；工程最新审阅已到V28/q0 factor continuation，本支不重复其reference逆/CSR，NN邻支本批不派活。

若所有路线效果门失败：停止本支这套低维粗修正加当前主子块RAS的组合微调，不自动又写一轮长准备。下一次重大机制应明确改变局部传输/波动粗空间的稳定性（例如物理阻抗传输与具备分辨依据的谱空间），需先说明如何区别于已失败方法；本批不实施它。若某路线通过：下一步先做同离散packet-only必要冷链与成本复核，再考虑中间尺寸/MPI；历史P6/L5空间精度FAIL、原尺寸目标和2TB/48h资格仍单列。不能因低RSS或预条件器名字宣布成功。

## 9. 外部依据及审阅端验证边界

[T1] Li–Hu，2025，[原始Maxwell-harmonic Schwarz论文](https://arxiv.org/abs/2501.18305)，只引用其阻抗/谱空间及适用条件，不给当前方法背书。

[T2] Greif–Rees–Szyld，[GMRES with multiple preconditioners](https://doi.org/10.1007/s40324-016-0088-7)，多方向最小残差背景；本批3列非线性PC不是其完整MPGMRES算法。

[T3] [PETSc KSPFGMRES官方说明](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)，支持非线性右预条件；现场保持已资格化ABI，不升级库。

审阅端只做小型complex128代数与文件结构/身份检查，没有运行本任务PDE、真实3列PC或收敛实验。GitHub视觉渲染未取得时记NOT_VERIFIED，不能为此阻断已获授权的数值执行或重跑PDE。
