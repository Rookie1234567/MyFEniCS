# Task43 V2 有限诊断计划

## 目的与边界

本轮只执行已授权的有限诊断，保留 Task43 V1 的 `PARTIAL / CONTROLLED_NEGATIVE`、9 次接受、R10 未过冻结噪声门，以及独立精度验证未通过的结论。任何 V2 结果均不回写 V1 选择链。完整模型最多 6 次：A1≤2、A2≤2、B≤1、C≤1；未用名额不自动转移。失败、进入完整 runner 后的前置失败、资源停止和重试都计入。原 R10 q8/q10 恢复采样不是模型尝试，但三次 watchdog 费用保留。禁止启动 NN、FTT、成本 campaign、迭代方法或 0.7 nm。

比较器只对已保存的完整输出作同一物理设置/同一点比较。R13 是 612 个 `(side,m,n,pol)`，R14 是 836 个；R14 的共同 612 逐键比较，额外 224 只作为 R14 的 tail 量测，R13 没有的系数始终是 `null/absent`，不补零。功率行核对 side、power-carrying、R/T 与聚合一致。比较不授予 continuum convergence、full-DtN 收敛、独立精度或选择资格。

## 冻结的物理问题、软件与环境

- 几何：周期 `x,y = 50 × 50 nm`，计算域 `z=[−10,130] nm`，全物理计算域体积为 `350000 nm³`；Si 长方体柱 `x=[16.5,33.5] nm, y=[15,35] nm, z=[0,120] nm`。空气 `n=1+0i`，基底与柱 `n=0.999002304859+0.00182649365i`，相应 `epsilon_r=0.9980022690345409+0.0036493427323206554i`；`mu_r=1`。波长 13.5 nm，入射 `theta=89°`、`phi=90°`、s 偏振、复振幅 1 V/m；E/H 单位分别 V/m 与 A/m。无相位拟合。体采样 E floor=`sqrt(350000)`，H floor=`0.002654418727984993*sqrt(350000)`，G floor=`sqrt(700000)`；端口幅度使用单位 incident-modal floor 1。q10 是主比较，q8 同点结果作为采样稳健性核查并分别记录，不称积分收敛。所有记录还绑定实际 resolved config 的完整物理 hash；摘要值不能代替 hash。
- 资格化执行环境：`source scripts/activate_task40_phi90_pord64.sh`；Python 3.12.3；PETSc 3.19.6，`complex128/int64`；DOLFINx/Basix 0.10.0；OpenMPI 4.1.6；MPI=1；OMP/OpenBLAS/MKL/NumExpr 均 1 thread；每个 worker 先限定 1 个可用 CPU，实际 CPU 与可用内存在各次 launch preflight 记录。禁止直接调用虚拟环境 Python 替代 activation。matching complex/int64 SLEPc 不存在且其 import 有注册冲突，但下列 direct 路径不需要 SLEPc；不重装/重建环境，也不把生产/full-suite pytest 门写成通过。
- 场采样点、输入背景、q/R 和空间身份均逐端点留 hash。incident、port 面和体积分分别记实际 q：起点 q15/q28，V2 加严 q19/q32；模式矩形 R13 为 `|m|≤4, |n|≤8`，R14 为 `|m|≤5, |n|≤9`。不得将 quadrature 或 R 混入物理 hash。

## 空间与求解核心身份

| 身份 | 空间与节点 | 已知规模／限定 |
|---|---|---|
| A1 R10 | Task43 variable-p condensed 路线；R10 原 solve 的 `3×10×6` 180 格、全 p6、118800 FE；实际轴 `x=[0,16.5,33.5,50]`, `y=[0,5,10,15,20,25,30,35,40,45,50]`, `z=[−10,0,30,60,90,120,130]` nm。 | 旧 R10 的41个 solver-recorded 数值源文件均与当前源逐 hash 相同；accepted parent / candidate-plan / R13 行身份固定。原记录的 materialized matrix route 是 `assembly_time_variable_p_condensed`、PETSc MUMPS、assembly-time 与 cell static condensation=true、Floquet slave elimination=true。采样恢复的 config 里这四种求解/重构设置不同；恢复配置只构造 mesh/P6 carrier，不是 solve replay。新 A1 必须显式还原上述 solve flags 与 MUMPS，不把恢复默认 false 当作新求解设置。 |
| A2 Y6_1 | Task40 native P6 condensed；`6×16×6`、576格、380160独立 FE=`120960 trace+259200 interior`；`x=[0,8.25,16.5,25,33.5,41.75,50]`, `y=[0,3,6,9,12,15,18.333333333333332,21.666666666666668,25,28.333333333333336,31.666666666666668,35,38,41,44,47,50]`, `z=[−10,0,30,60,90,120,130]` nm。 | 必须通过逐依赖源码、弱式/边界、约束、quadrature、空间与 direct-route 身份核对，证明所选 native P6 路径是该基线的可比延续；不能因 R10 A1 或变量-p资格自动覆盖。新 A2 endpoint 各须有自己的 live-factor 额外一次 same-LU 输出不确定性核验。若来源/核心或 live-factor 门无法建立，A2 记未资格化并停止受影响端点；不得改走 variable-p 后归因为 q/R。 |
| B R9 父状态 | R9 是 180 格 mixed-p：28 个 p5、152 个 p6；原 `q15/q28/R13`。其真实 variable-p 核与 A1 配对核的版本/plan/FE/输入 hash 单独绑定。 | 不称 all-p6；不声称 root 的任何核验已证明它与 Y6_1 native-P6 是同一个 solver core。B 的主效应比较是同一 R9 variable-p 路径的 parent→单次 h 候选；与 Y6_1 的对比另标跨离散/solver-route 的有限完整向量差，不叫同核等价。 |
| C 新 h-rich 参考 | 预先固定 uniform-p6 `9×16×6`、864个六面体；`x=[0,5.5,11,16.5,22.166666666666668,27.833333333333332,33.5,39,44.5,50]`, `y=[0,3,6,9,12,15,18.333333333333332,21.666666666666668,25,28.333333333333336,31.666666666666668,35,38,41,44,47,50]`, `z=[−10,0,30,60,90,120,130]` nm。 | 周期 x/y、开放 z 的实体计数公式给独立 FE 预测 `648×864 + 72×(9×16)=570240`，trace=181440、interior=388800；这是推导预测，mesh/DoF 构造后须实际核验。该规模约为 Y6_1 的1.50倍、R10的4.80倍，可能超过 B 的候选 FE 上限；C 是参考，可超过237600。Task40 axis-catalog 检索只发现 Y6_1/Y6_2 的 `6×16×6`，现有已揭盲 Task43 清单未见此精确网格；这是范围有限的新颖性检索，不声称全局从未生成。正式 runner 之前仍须检查完整已运行/ignored 清单和实际资源预估。 |

## 固定阶段、比较方向与解锁

| 阶段 | reference → test | 唯一变化 | 计数 |
|---|---|---|---:|
| A1-q | 原 R10 `q15/q28/R13` → 同一 R10 空间 `q19/q32/R13` | 体 q15→19；incident/port q28→32 | 1 |
| A1-R | 本轮新 R10 `q19/q32/R13` → 同网格 `q19/q32/R14` | DtN 矩形 | 1 |
| A2-q | Y6_1 原 `q15/q28/R13` → native P6 同空间 `q19/q32/R13` | 体与 incident/port q | 1 |
| A2-R | 本轮新 Y6_1 `q19/q32/R13` → 同网格 `q19/q32/R14` | DtN 矩形 | 1 |
| B | frozen R9 parent → R9 同变量-p/同 q15/q28/R13/同核心的单种子 h 候选 | 仅该固定 h 动作与其闭包 | 1 |
| C | 固定新 C uniform-p6 网格 | 一次完整参考解；q19/q32/R14 固定 | 1 |

A1 的旧 baseline 场必须使用原 R10 保存系数，经本轮 attempt3 已 hash 绑定的恢复实现，在同一 q8/q10 体积 Gauss 点恢复；不借用 Y6_1 或 6×10×6 controls。其依据为原 R10 accepted-parent/candidate-plan/active-degree-map、storage 和 612 rows 身份，非从系数前缀近似。旧 source 41项同核只覆盖记录列出的 solve sources，不表示整个机器/转移依赖闭包均相同。A2 只能在通过上表身份门后，用真实 Y6_1 原系数/同 native-P6 restore 路线形成其对应相同物理 q8/q10 baseline；若身份不完整，不解 A2。

A1/A2 的 q 扰动超过10%时，只要硬残差、资源和基线门都过，仍做本组预定 R 扰动，以区分原因；q/R主比较始终使用该端点既有 solver-normal-correction 策略完成、额外诊断 correction 开始之前的场。A1 每端点保留原有的一次常规 solver correction；A2 保留 native Task40 的 `max_same_factor_corrections=2` 策略，即初始求解后最多再做两次常规 correction（最多三次求解），并记录实际次数；Y6_1 历史记录实际只做了一次 correction。额外 correction 只用于核查同因子输出不确定性，不替换 q/R 主端点，也不能择优采用。若 A1_q 的 q 扰动或 extra-LU 不确定性门失败，但硬残差、资源和基线门通过，仍按预定方案完成 A1_R 并记录原因；失败后锁住 B/C。硬门失败、基线不可信或资源门失败则停止受影响分支，不自动重试、不将失败挪到另一个因素。A1/A2 的全部 q/R 比较及 extra-LU 输出不确定性门都通过才解锁 B；B 还要求同 R9 variable-p parent/candidate 的 plan、space、solver-input 门通过且 candidate 实际 FE `<237600`。B 不替换 seed、不随误差排名调整。

B 的 seed 固定为 R9 G²贡献最高的 global cell 8，原 storage/plan/record 的三哈希已绑定。saved geometry 实际 bounds `[16.5,5,−10]→[33.5,10,0] nm`，parent p5；原 comparison 最大贡献 `1.3895613869617563e−5`。依据 `benchmarks/artifacts/task43/v2_root_audit/seed_geometry_audit.json` SHA256 `3fc78f7d728f357fc33b26decd0e6aaa5d3981197cdef4dc49f83633c169a524`。只作一层 h 闭包，周期与2:1 closure按已验证 builder；先实际构造并数FE、closure与资源，超过 FE 门即停止，不替换 seed。B 只有在同一数值核心资格证据同时覆盖 R9 parent、h candidate 与比较 reference 时才解锁；当前可见核验没有证明 R9 variable-p 与 Y6_1 native-P6 同核，因此该门目前未通过，不能用有限输出措辞绕过。若没有真实同核/等价审计通过，B 不运行。R9 与 Y6_1 核心未证等价前，不把二者交叉差叫作同核 spatial effect，也不移植 R10 的求解/接受资格给 R9。

C 是新的 uniform-p6 richer witness，不是 B 的镜像 seed，也不根据 B 结果选网格。C 只有在 B 已产出可用、通过身份与硬数值/资源门、且候选计划、mesh、完整输出和 SHA 均冻结的候选后，才可启动并与之比较；B 未解锁、失败、受控停止或没有可用冻结候选时，C=`not_run`，不为缺少候选单独运行参考解。固定 q19/q32/R14、native uniform-p6 直接路线与上表实际 axes；其一例无法自行证明 q/R 误差低于终公差，故 C 只形成完整向量的有限比较，绝不借用 A2 的 q/R 资格。C 与 B 的预定 q/R 不同，若二者都运行，C−B 是空间、q 与 R 的混合差异，不能归因纯空间。C 可用于展示新h-rich参考的有限独立观测，但不称独立精度通过。C 运行前必须检查精确网格未揭盲/未运行范围并依据实际 rows/NNZ、同 ABI MUMPS direct结构预测作内存/墙钟预估；无法保守地落在计划门内时，C 不启动。C 一次名额不用于临时改网格或重跑。

## 输出比较门与残差

每个端点保存完整 R/T/A_volume、R00_s/p/total、612/836逐通道复幅与 power、四组 top/bottom×s/p端口幅值、总/散射 E/H与物理 G、原始场和共同 q8/q10 点。`A_volume` 必须来自独立材料体吸收积分并与端口 R/T 分开；只做旧 record 算术复核时注明来源，不冒充重新积分。采样必须使用同一 q 点、同一背景和物理 hash；跨网格仅要求物理配置与采样坐标/背景一致，另保留各自 discretization hash。

A1/A2 q/R 加严按 `outcomes/records/comparison_contract_v1.json` 最终容差的10%作扰动门：R、T、A_volume、R00_total各≤1e−6；R00_s、R00_p、逐通道功率≤1e−7；端口四组复幅入射模态地板相对L2≤1e−5；全/散射E/H、物理G使用同一incident floor≤1e−5。端口幅组是顶部/底部散射模态，不是垂直材料侧壁。

R13→R14除了共同612输出，新增224必须独立保存每行复幅、功率与per-side聚合功率；R13 中这些键严格 absent/null，tail 不产生“相对R13的绝对差”。每项 tail channel power≤1e−7，每侧 aggregate≤1e−6；tail amplitude 各组实测 L2 幅度以固定 incident-modal floor 1 作分母≤1e−5。共同模态差仍按原参考幅度与floor计算，并强制联合扩展包络 `sqrt(common612_delta_L2²+tail224_amplitude_L2²)/max(R13_reference_group_L2,1)≤1e−5`。共同与tail通过不代表 R14 已具完整 DtN 收敛。

所有新解的 solver gates：完整 active-space explicit true residual≤1e−8（保留 direct 原目标），A6 必须从独立原方程计算并≤1e−8；condensed residual≤1e−9；能量闭合 `abs(1−R−T−A_volume)≤1e−5`。不能用求解器递归残差/condensed residual 替代 A6，也不能用 `1−R−T` 回填吸收。

新 A1、A2 每个 solver endpoint 最多额外做一次同因子 correction，与该端点原有 solver-normal-correction 策略分开记录。q/R主比较用正常策略结束、额外 correction 前的完整输出。A1 的正常 correction 固定为一次；A2 保留 native Task40 的 `max_same_factor_corrections=2`（初始求解后最多两次 correction，最多三次求解），并记录实际次数；历史 Y6_1 实际 correction 数为一。额外 correction 修正前后都重算完整显式 `b−Ax`、同rhs归一残差、独立A6原方程、condensed residual、R/T/A、所有模态和完整 q8/q10 场量。资格需同时满足：两端 `b−Ax` 和归一残差有限、修正后严格下降；修正前后 A6 均≤1e−8、condensed均≤1e−9、closure均≤1e−5；before/after完整物理输出差逐项≤最终容差10%。额外 correction 的失败记录为代数输出不确定性未受控；若端点硬门通过，仍依预定 q/R分支完成剩余 A 因素，但锁住 B/C。只允许一次额外 correction，不复用 A1 结果声称 A2 已过。R14端点的same-LU comparison使用836 expected keys；V1默认仍612。

求解器自带的常规 correction 也从记录的原始数据复核：初始/修正后的显式残差范数与 RHS 相对值必须有限且都严格下降，`solution_updated=true`，correction KSP 收敛原因必须为正值；不能只采信 `status=passed` 标签。

R14 tail/common 的 same-LU变化按同一端点 inventory比较；同因子变化也须纳入联合(common+tail)扰动。所有残差/输出门均由 checker 从原字段重算，记录 `pass/fail/not_run` 与每个失败的实值和限值。

## 侧壁资格（与端口幅值门区分）

Task43 comparison contract 中的 canonical sidewall 是**四个垂直材料界面，每个界面的双材料侧**：x=16.5/33.5 nm面，y=15/35 nm面；距界面0，按材料内/空气侧选定 cell 的单侧复 E/H数学迹；每面按两网格切向断点并集作 tensor Gauss q8/q10，Gauss点避开角边；各面/各材料侧 E/H 复幅 surface-L2，以相应 incident surface norm 作分母地板。此项当前为 `NOT_MEASURED`，没有已经验证的 one-sided sampler。top/bottom端口模态、4个端口振幅组、volume场差都不能替代它。本轮不开发sidewall sampler；即使 B/C其它指标通过，整体侧壁资格仍保留缺口。

## attempt资源、墙钟与停止

Task43 单重型流程用资格化 native-capacity gate：绝对同时 process-tree/cgroup RSS上限192 GiB；先读实际 available/total，保留 `max(64 GiB,15%有效总内存)`；launch cap=`min(192GiB,80%有效总内存,available−reserve)`，planning cap=`min(192GiB,75%有效总内存,launch cap)`。这些来自 `src/io/native_capacity_profile.py` 的 `task43_hp_adaptivity_resource_v1`；worker 实际 launch 数值入记录，不能把192 GiB当作每次可用内存承诺。Task-tree VmSwap必须始终为0；global swap只观察不归因；一次一个 heavy，taskset 1 CPU，MPI1/thread1，reserve实际不足、规划超cap或出现task swap均在相应阶段停止并清理进程组。

每模型墙钟是完整 subreaper watchdog 的 whole-wall，不是 solver内部计时或把phase求和：

| 阶段 | whole-wall硬上限 | 尺度依据与边界 |
|---|---:|---|
| A1各次 | 7200 s | 同一R10 118800 FE；R10已完成whole-watchdog为2588.517 s，7200约2.78倍，可覆盖启动/网格/端口/采样/单extra-LU；这是停止上界而非预测。 |
| A2各次 | 7200 s | 同Y6_1 380160 FE=`120960+259200`；已知1905.877 s是native direct summary的内部runner时间，不是whole-watchdog。上界是该内部时间的3.78倍，并给完整watchdog/输出留额外空间；没有将1905.877宣称whole wall。若A2预估明显超cap，不启动。 |
| B | 7200 s | FE严格低于237600（<2.0×R10），R9历史whole-watchdog 2878.935 s；7,200约为2.5×R9全工作流、2.78×R10，留出h closure与输出余量，非时间线性预测。 |
| C | 14400 s | 预测570240 FE（约1.50×Y6_1的380160 FE、4.80×R10），没有同尺度Task43 whole-watchdog校准。14,400是7200的2倍并约5.56×R10实测全工作流；只有实际MUMPS rows/NNZ/可解释fill forecast在动态planning cap内才允许运行，不把比例当memory上界。forecast无法保守通过就不启动C。 |

C 还依赖 B 的已完成候选：即使 C 自身新颖性与资源预检通过，只要 B 未解锁或未形成上述可用且 hash 冻结的候选，C 仍记 `not_run`。

PDE attempt监控上限分别按此表固定；不得因运行慢临时延长。任一失败不重启同一case。官方resource result报告同时给whole-watchdog、内部solver时段、最大同时RSS、swap、exit、descendant cleanup与资源输入身份。

## 证据与冻结合同

正式解前，root独立审阅并批准本 Markdown 和同版本 JSON contract；两者固定 SHA 加入每次 launch preflight，承诺冻结后不改判据。正式 artifact 写 `benchmarks/artifacts/task43/v2_diagnostics/{phase}_attemptN/`，轻量 records 写 `docs/task43_hp_adaptivity/outcomes/records/`。保存完整command/env/source、R10/Y6/R9 parent输入、mesh/plan/DoF/rows/NNZ、物理/离散hash、q/R、同因子 before/after、全向量、文件SHA、resource summary和人工/自动停止说明。最终 response_v2逐项覆盖Q01–Q08、tests与原negative分类、6次预算使用、每条资格状态与边界。V1 review/response/accepted record不可改写；最终没有新结果时仍保持V1状态。
