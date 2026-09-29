# Review V2：Task042 V4 审阅与空间覆盖／投影补空间失效定位

## 0. 决定、身份与本批要消除的不确定性

**接受 V4 为有范围限定的数值负结果；两个两层粗逆仍不合格，不批准 production 或合并。本批固定原算子、几何局部 PC 与两个空间，通过同向量对照定位失败机制，不再直接增加网络、空间或求解次数。**

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task42_neural_coarse_inverse
worktree                   = /home/fenics/Projects/NN-Lab
review_date                = 2026-09-29
reviewed_HEAD              = c3bcb0e6b9eec87eca3bdeb54f71d524c01a6ceb
original_base_SHA          = ccd357885f7f9be84efe3be07868cc94f13d93fc
previous_review            = review_report_v1.md @ 333f6aa966284831a68d68afd6a231152fbcc824
latest_response_reviewed   = response_v4.md
V4_P0_P1_source            = 8b792d78b06903ef874fbcf14fa06d951ae9c2ff
V4_P2_P3_source            = 5691d79abe87d3582ede5bbaf8369c5487e7c392
research_record_review     = ACCEPTED_WITH_LIMITATIONS
existing_solver_gate       = NOT_QUALIFIED
new_execution_batch        = V5_FIXED_OPERATOR_FAILURE_LOCALIZATION
response_required          = response_v5.md
new_NN_or_basis_training   = NOT_AUTHORIZED
new_full_KSP_campaign      = NOT_AUTHORIZED
fresh_pool_and_F5          = NOT_AUTHORIZED
master_merge               = NOT_APPROVED
```

最终目标仍是约 2 TB 整机物理内存内求解 0.7 nm、周期单胞任意非可分三维 Maxwell。**本批是求解器／预条件器的诊断旁支：判断无全局 p4 LU 的两层方案失败，主要证据指向空间覆盖不足、投影对局部作用的不利改变、补空间局部作用薄弱，还是它们的组合。** 不是新的精度资格、神经加速或 0.7 nm 容量通过。

本审阅实际依据远程合同、response/outcomes、轻量 records 和相关源码；未 SSH 重跑工作站，未重新计算所有 ignored 数组的 hash。文中 measured 指仓库记录；公式推导和小矩阵反例不冒充真实 Maxwell 测量。本批执行时须实际核验被复用 artifact，不能只信摘要状态。

## 1. 权威、覆盖与范围

先读根／目录 AGENTS、[仓库原则](../repository_work_principles.md)、[task.md](task.md)、[Review V1](review_report_v1.md)、最新 response/outcomes 和本 review。原 task、Review V1、response_v1–v4、V1–V4 数值 records 逐字保留。

本 review 接续 Review V1 已结束的 V4 批次，**只解锁下面 D0–D4 的固定对象诊断，不重复 P1 捕获、P2 建基或 P3 六次长求解，不启动 P4 未用终测**。继续保留“不要求局部 PC 先收敛才能研究全局机制”；既有失败不重新归类为成功。V5 指版本批次，不是原 task 中的 F5/p6 阶段。

[用户受控共享授权](outcomes/shared_authorization_v2.md)及[上一 review 的资源规则](review_report_v1.md)继续有效：其他 heavy 存在不是一刀切阻塞；Task042 自有 nonblocking lock、内部顺序执行、CPU-only、MPI1、数学线程1、现场选空闲物理核、自身 nice10/idle I/O。保留整树 RSS hard16 GiB/warn12 GiB、own swap0、无 OOC、系统 reserve 与邻增长规划128 GiB、磁盘至少50 GiB、artifact总量不超过20 GiB。无 cgroup 委派时如实使用0.5 s采样停止，不声称连续内核限额。只停止本任务后代，不动邻任务、锁、环境、亲和性、优先级或 watchdog。不升级 ABI／CUDA，不重装 F0，不建后台等待器。

**本批不输出新 production PC，不改 NN 权重或 Z/U/R，不调整 patch、overlap、port、shift、范数权重、rank、restart 或容差；不使用在线 teacher、global p4 factor、全局 dense S/B/C/投影矩阵或 private audit CSR。** 诊断函数调用原 B/C/B2 及小规模最小二乘是允许的，不代表授权新的迭代求解算法。

## 2. V4 已证实什么，尚未证实什么

主要依据：[Response V4](response_v4.md)、[中心结果](outcomes/two_level_global_error_v4.md)、[summary](outcomes/summary.md)、[独立 Gate](outcomes/records/gate_decisions_v4.json)、[空间自检](outcomes/records/coarse_space_algebra_v4.json)、[快照清单](outcomes/records/training_snapshot_manifest_v4.json)。

| 固定已消费诊断 RHS | V3 GEO 原A4相对残差 | V4 OLDPOD 原A4相对残差 | V4 ERROR 原A4相对残差 | 数据身份／判断 |
|---|---:|---:|---:|---|
| physical_PH_b6 / 0 | 0.891957825531 | 0.998588187270 | 0.999863649936 | measured，均未达到原1e-10 |
| port-only / 10 | 0.935861877336 | 0.949242609663 | 0.937175812499 | measured，均未达到原1e-10 |
| mixed / 11 | 0.932010701839 | 0.905073739084 | 0.901084822725 | measured，均未达到原1e-10 |

两条 V4 候选共6项均256步、strict0/6。OLDPOD物理RHS固定Schur相对残差在32步约0.999092825721、256步约0.999092817197，平台明确。空间内恒等式、真实S/native/恢复配对通过；rank均128，R条件数约334/586。整树最大1128828928 B、own swap0，无新NN训练；不是内存触线或训练预算耗尽。新终测、p6外层、R/T/A/A_volume、正式E/H和通道终态仍未运行。

审阅解释必须分层：

| 层次 | 本次判断 |
|---|---|
| 已确认 | 当前B＋两个固定Z的两层组合没有获得有效全局收敛；物理RHS比B单独更差 |
| 数学风险 | 双侧投影会改变局部作用；空间内精确性不保证补空间可逆或收敛 |
| 待测假设 | Z/SZ覆盖不足；局部有用作用被投影截去；补空间局部作用自身薄弱；目标尺度与非正规效应等 |
| 禁止直接断言 | 真实B2已经奇异、128维必然太小、某特定Maxwell模态已确诊、所有两层或神经方法无效 |

本轮 Codex 按 Review V1 正确实现并触发停止流。**ChatGPT 在此修正研究判断：加入一个基并不等于单纯扩充原 Krylov 搜索空间；当前平衡组合会改写 B，退化风险需要实测，不能只用四项恒等式替代。** 不把这一设计风险伪装成已发现的代码 bug。

## 3. 冻结对象与可检验的数学关系

| 对象 | 固定身份／界限 |
|---|---|
| 物理／离散 | original Si，13.5 nm，1度/phi0/s；p6/h10对应同网格p4；252cells、quad15、双Floquet、完整80 DtN；材料和几何沿原task |
| S | p4独立凝聚trace＋port，21824行、8184464存储NNZ |
| S CSR SHA | `150f18e26f15783726f2ffeb362ef053450962a16fff13d5241cc93c8d018560` |
| physical SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| mode SHA | `d4380495d912f97f6d303a85756bb9b252a1117bad229b559f0ac8140e745fbb` |
| B | V3 `R-GEO-CELL80-v3`；252个最多272行局部主子块、canonical限制／次数平均延拓、全部80port，不改其数值实现 |
| 两套Z/U/R | V4-P2已冻结OLDPOD与ERROR的`basis.npz`；按空间record读取精确path/source/hash，不重新POD/训练/编码 |
| 原验算 | 原A4、累计端口、内部恢复、slave、identity和complex128；原strict1e-10不变，但本批不授予新strict资格 |

参考实现：[两层核](../../src/solvers/learned_two_level.py)、[几何核](../../src/solvers/learned_geometry_overlap.py)、[原p4](../../src/solvers/learned_coarse_runtime.py)、[V4编排](../../src/runners/task042_two_level.py)、[native映射](../../src/solvers/learned_coarse_data.py)。所有符号均在同一canonical reduced trace＋port空间；原物理A4与S不能混称。

### 3.1 需要追加验证的关系

对每个空间定义如下。逆记号只表示原三角求解，不物化逆；Pi也仅以U乘法作用。

```math
SZ=UR,\quad U^HU=I,\quad C=ZR^{-1}U^H,\quad
\Pi=UU^H,\quad E=I-\Pi,\quad H=SB,\quad
B_2=C+(I-CS)BE.
```

由SC=Pi直接推导：

```math
SB_2=\Pi+EHE,\qquad
B_2r-Br=Cr-B\Pi r-CSBEr.
```

这说明粗空间内由单位作用处理，而U正交补由T=EHE处理。**T在整个空间必然消去U，所以不能把全空间T的零特征值当作新发现；只允许在U正交补中检查。** R条件数是SZ编码的条件数，不是S、SB2或补空间T的条件数。

必须增加一个纯数组反例，验证“旧四恒等式通过仍可能失效”：S=I2，B交换两个坐标，Z为第一个坐标列。此时B可逆，但B2=diag(1,0)。反例只证明缺少一般保证，不证明真实Maxwell B2奇异；再加一个补空间正常的对照，避免诊断器总是报告投影有害。

## 4. D0：一次必要核验和固定共同状态库

完成必要Git/ABI/资源及artifact核验后，直接构建与原SHA一致的p4-only runtime。不要因为文档HEAD变化重跑旧P0/P1/teacher、安装环境或重组p6。核对原B和两层核的数值源码blob未改变；诊断扩展放独立research opt-in模块，默认求解器不变。

共同库按下列固定顺序，最多12个状态，不能为获得好看结果选样：

| 状态来源 | RHS | 数量／角色 |
|---|---|---|
| reduced零初值 | 原index0/10/11 | 3；full场按同一原RHS做particular recovery，不假定所有full分量为零 |
| V3 GEO最终失败state | 同0/10/11 | 3；使用既存failure packet，不重跑GEO |
| V4 OLDPOD最终失败state | 同0/10/11 | 3；使用既存failure packet |
| V4 ERROR最终失败state | 同0/10/11 | 3；使用既存failure packet |

读取实际run index和`failure_000/010/011.npz`，不猜造缺失路径。每项核对RHS family、scale、operator和packet hash，从full FE＋port提取canonical x，重算b_S及r=b_S−Sx；独立恢复与原残差配对目标仍1e-10。**不能从标量历史反推缺失向量，也不能为了补齐中间快照重跑长KSP。** 某state缺失时标missing，仅保留可验证子集；原S/B或空间身份不符则停止受影响路线，不使用旧近似文件替代。

保存每项x/r/RHS/source的hash、实际幅值与单位、归一化及来源。以同一库逐项喂给B、两个C及两个B2，才是同向量对照；不能用各方法自己不同的末端残差作直接因果比较。所有这些问题已消费，仅为诊断，不宣称fresh。

D0 pure-array测试包括复共轭/相位/尺度、零向量、输入不可变、两条新恒等式、反例与正常例；真实S只做必要少量配对。测试通过后直接D1–D3，不以旧残差仍为量级1阻止。

## 5. D1：覆盖检查——解空间与残差空间分开

对两个冻结空间和共同库每项计算：

```math
\eta_r=\frac{\|Er\|_2}{\|r\|_2},\qquad
\gamma_r=\frac{\|U^Hr\|_2}{\|r\|_2},\qquad
\eta_r^2+\gamma_r^2=1.
```

记录绝对范数、分母、恒等式缺陷及原r−SCr直接配对。零r按exact-zero分支，不除一个人为有利常数。eta_r是当前残差在空间像之外的比例，不是全局收敛率；eta_r接近1不能单独证明空间毫无价值，小幅但关键谱分量也可能重要。

另外授权**只读复用V2已消费index0/10/11的准确teacher，进行离线解误差覆盖审核**；这是诊断例外，不授权读取seed420620新池、不授权新reference LU或重新生成数据。按实际family与normalization严格匹配，先复算其原A4/port/恢复。缺失即将解误差列标`not_available`，仍继续无teacher的残差诊断。

令e=x_star−x，Qz是同一Z空间的正交基（已有Z正交性通过可直接用，否则仅诊断QR，不改checkpoint）：

```math
\eta_e=\frac{\|e-Q_zQ_z^He\|_2}{\|e\|_2},\qquad
Se=r-r_{\star},\quad r_{\star}=b_S-Sx_{\star}.
```

保存teacher残差项，不能默认其精确为0；严禁把e误当r或混用full与reduced坐标。teacher只存在离线覆盖进程，向后输出覆盖标量与hash，不输出可供PC读取的测试解／系数。D2/D3进程不加载teacher。不得将这些测试误差补进Z、更新basis或用作后续独立测试的初值。

## 6. D2：同向量交叉作用与低维最小二乘反事实

每个共同r分别求d_B=Br、d_C=Cr、d_2=B2r。报告其范数、S像、与r的复内积，单位步以及最优复标量步长下的Schur剩余比例：

```math
\alpha_d=\frac{(Sd)^Hr}{\|Sd\|_2^2},\qquad
\rho_{\rm unit}(d)=\frac{\|r-Sd\|_2}{\|r\|_2},\qquad
\rho_{\rm opt}(d)=\frac{\|r-\alpha_dSd\|_2}{\|r\|_2}.
```

Sd为零／极小时按固定数值秩规则处理，记录scale和跳过原因，不产生无限系数。最优标量仅是探针，不反馈KSP。分解B2r−Br的三个项Cr、−BPi r、−CSBEr，记录各S像、和的配对缺陷及相互夹角／抵消；不能单凭某项范数很大断言它有害。

同一r再做两种小最小二乘诊断，回答“保留局部方向能否优于当前固定组合”：

```math
\rho_{BC}=\min_{\alpha,\beta}\frac{\|r-S(\alpha Br+\beta Cr)\|_2}{\|r\|_2},\qquad
\rho_{ZB}=\min_{c,\alpha}\frac{\|r-S(Zc+\alpha Br)\|_2}{\|r\|_2}.
```

其搜索空间分别含原单方向Br，所以精确最小二乘有rho_ZB<=rho_BC<=rho_opt(B)。rho_ZB还不大于eta_r。通过独立原S作用核验这些包含关系；发现超过舍入／固定秩阈值的违反应先查诊断实现，不归因Maxwell。

只做最多2列／129列的QR或薄SVD，固定相对1e-10秩阈值，报告列尺度、数值秩、最小残差和系数；依赖列按该规则确定性处理。允许诊断用的小最小二乘最小范数解，不允许全局伪逆或把它接为production fallback；不形成法方程。利用已有SZ=UR可避免长期持有另一个n×129副本。

对每个诊断修正，用原RHS恢复x+d的完整FE与累计port，独立报告native、port绝对与operation-relative、原固定参考尺度、内部恢复及identity。选择alpha/beta/c只基于完整Schur欧氏目标，不事后按native/port挑参数。固定尺度为零时报告绝对量或undefined及原因，不能静默改成一个看似良好的相对数。

**这些是从同一个已存state出发的离线反事实，不是新完整求解；不得输出“新PC已收敛”或official物理结果。** 若rho_ZB明显更好，只支持“保留这些方向的搜索值得研究”，不证明一个新augmentation算法已获得全局鲁棒性。

## 7. D3：补空间作用审计——看完整像，不只看小投影矩阵

每个空间预登记最多16个探针：共同库12个r经E投影、规范化后的方向，另加固定seed420805的4个复随机方向再作E投影。顺序固定；零或依赖方向按相对1e-10剔除，不随机补足、不扫描seed。对剩余方向做薄QR/SVD得到V，确认V^HV=I、U^HV约0，报告有效rank和每列来源。

计算同一组输入的完整n×k输出：

```math
Y=HV=SBV,\qquad Y_{\perp}=EY=TV,\qquad Y_{\parallel}=\Pi Y.
```

记录三者的范数、奇异值、正交分解缺陷。可同时记录小矩阵V^H TV，但**不能只因它近奇异就说T近奇异**：它可能遗漏V以外的输出。主要依据必须是完整Y和Y_perp。

对Y_perp的最小右奇异向量w，取v=Vw，独立重算Hv、Tv和Pi Hv，比较其绝对大小、Tv/Hv比例、保留与丢弃的方向。这样得到的是“所抽样补空间上的弱作用见证”；数值很小且Hv明显不小时支持投影衰减，二者都很小时更支持局部B本身作用薄弱。不存在小值也不能排除未采样方向，不能报告完整S/B2/T的条件数或全局最小奇异值。

额外用同批v检查SB2v=Tv和B2作用的真实一致性，操作尺度缺陷仍以1e-10为检查目标。不要加入完整特征值求解、shift-invert、逆迭代、SVD全矩阵或其他大factor；本批不执行新Arnoldi/Krylov campaign。

## 8. D4：证据归因，不强迫唯一结论

| 可能证据组合 | 可写的结论 | 不能据此声称 |
|---|---|---|
| 所测eta_e/eta_r偏大，Cr及Z＋Br诊断也无实质改善 | 这两个空间在这些方向上覆盖／利用不足 | rank128普遍不够、所有全局空间无效 |
| 同r下B2比Br更差；保留Br的最小二乘更好；投影分解显示相关抵消／衰减 | 本批支持组合／投影退化假设，值得下一轮比较保留搜索方向的组织 | 已经证明真实B2奇异或新augmentation已成功 |
| 完整TV弱而同方向HV明显不弱 | sampled complement上有投影衰减见证 | 完整算子谱根因已确定 |
| HV与TV都弱，覆盖修正亦不足 | 局部B和空间共同不足的证据 | 只需换GPU、训练更久或松弛残差 |
| 指标冲突、参考缺失或样本不足 | `INCONCLUSIVE`，列缺失的最小信息和范围 | 为交付强行选一个唯一根因 |

因果判断必须引用具体相同r的行、绝对量／分母、数值容差和源码；不把为消除粗分量而正常丢弃的像自动称作有害。报告coverage、fixed-combination、local-complement三项分别为supported/not_supported/inconclusive，允许并存。不要为了获得某个状态临时调百分比阈值；明确展示连续指标及差异相对数值误差的大小。

本批的“通过”仅指诊断自检、数据身份和有界执行合格，不是solver pass。所有原strict返回1e-10 Gate及0.7 nm/任意3D/F5边界不变。完成后根据证据建议**唯一下一最小试验**，但本批不自动实现新的PC、augmentation、换基或训练。

## 9. 成本控制、停止条件与提交

优先复用现有局部因子构建接口、残差审核器、runner与watchdog；数值诊断核心进入独立src/solvers模块，编排入口为显式research profile。固定对象顺序加载，两个空间不同worker或明确先释放再切换；不让两个basis及teacher长期叠加。

原局部因子约302047392 B、每空间Z＋U89391104 B、小R262144 B均需实际核对；继续全部局部／bottom因子<=512 MiB、表示／索引／诊断workspace同时峰<=512 MiB，整树16 GiB。共同库最多12个n维state/residual可流式读取，probe矩阵最多n×16；不得读取全部384对full teacher或复制整个audit CSR。构建前预算把129列最小二乘工作区、解压和LAPACK临时量计入，不以仅权重大小代替RSS。

每个新真实FE诊断阶段仍经`python scripts/run_case.py input/task042_neural_coarse_inverse/<one-run>.dat`。一dat对应一个明确stage、固定operator、对象／RHS清单，不隐藏长迭代扫描；纯数组测试无需伪装FE dat。源码在正式负载前clean commit；记录真实source，文档HEAD不能冒充run source。

建议阶段仅D0核验/packets、离线teacher覆盖、OLDPOD诊断、ERROR诊断和只读聚合；不为每个指标复制runner或重建runtime。S/B/C调用和审核/IO/setup/释放分项计费，嵌套计时不重复累加；只记录需要的有限指标，无每步大日志。所有时间为shared-workstation，不据此宣称神经提速、严格解成本或绝对零邻影响。

对象身份改变、真实关系不符、非有限值、diagnostic包含关系严重违反、资源或监督触线时，保存原因停止受影响阶段。缺少某个旧state/teacher只缩减相应诊断，不影响其他有证据的部分，不以重跑长solve补缺。明确实现bug允许一次记录充分的最小修复与针对性复查；有限试验未给出唯一根因不是bug，不扫描到得出偏好结论。

建议提交C1：配置/纯代数诊断/反例测试；C2：原对象适配与有限实测；C3：独立重算/证据/response。仅本分支、精确refspec推送；不amend/force/rebase/merge、不改旧task/review/response或旧数值记录。继承的无关文档checker错误保留，不做全仓清理、full pytest或重跑旧昂贵Gate。

## 10. 最小交付与 Response V5 必答项

```text
response_v5.md
outcomes/failure_localization_v5.md
outcomes/records/localization_design_v5.json
outcomes/records/common_state_manifest_v5.json
outcomes/records/coverage_v5.csv
outcomes/records/same_residual_actions_v5.csv
outcomes/records/complement_probes_v5.json
outcomes/records/localization_decisions_v5.json
outcomes/records/run_index_v5.json
outcomes/summary.md
outcomes/test_summary.md
```

仅提交compact标量、source/hash与必要小摘要；full state/probe/reference/basis在ignored目录，不在多份JSON复制完整历史。同步本Task042的development_progress与model_registry新段，V1–V4原文保留。run index绑定input_original、resolved_config、manifest、input/physical/source与model/hash、环境/线程/affinity、监督口径、停止／释放和原artifact。

Response首先回答：真正可用的共同state有几项；两个空间对**同一组**r/e覆盖怎样；B/C/B2的同向量作用和保留方向最小二乘说明什么；补空间弱作用是否有完整像见证；哪些仍不能确定；下一最小试验应只改哪一项。把pure-array反例、真实作用证据、预测与not_run分开。

旧seed420620终测继续unconsumed，本批不得生成或读取。G-neural、fresh qualification、F5、短波、official场/衍射全部not_run。完成D0–D4或遇真实停止条件即交付，推送后等review，不自动续跑。满足前置条件可直接执行本批，不逐小步等待许可，也不恢复“有heavy就只做F0”。

## 11. 方法依据与明确限制

本批两条新恒等式与反例由§3直接推导。方法背景可参考Gaul、Gutknecht、Liesen、Nabben，*A Framework for Deflated and Augmented Krylov Subspace Methods*，SIAM J. Matrix Anal. Appl. 34(2), 495–518, 2013，[DOI](https://doi.org/10.1137/110820713)，[开放预印本](https://arxiv.org/abs/1206.1506)（核对日期2026-09-29）。该文区分deflation/augmentation及其breakdown问题，不能当作当前B2或本Maxwell模型有效的证明。

**本批目标是用冻结对象、可复核的同向量证据缩小失效机制范围。不能以“算法自检通过”代替“补空间有效”，也不能以一个小矩阵反例代替真实根因测量。**
