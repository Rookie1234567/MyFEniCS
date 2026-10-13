# Review V46：停止扩容与单核续扫；一次联合神经更新的有界裁决

## 0. 决定与冻结身份

接受V46完整实施与数值FAIL。新增修正网使散射场误差降低，但学习与冻结控制几乎相同；不再追加网络、宽度、rank或原300+900单核轮次。本次仅授权：**保持已存双网络和全部物理不变，对修正网的隐藏层及三轴输出系数作联合、受阻尼控制的更新，并与冻结隐藏层的联合输出更新比较。**先通过真实导数/试步资格，再运行；不能只交接口。若仍无强数值信号，关闭该固定FTT求解组合，不自动再开同类变体。

```text
repository          = Rookie1234567/MyFEniCS
branch              = task42extra_feinn_5nm
canonical_worktree  = /home/fenics/Projects/NN-Lab-V2
base_SHA            = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
reviewed_HEAD       = 0efeaa97f6a2e109ef981c14dd3f7bc65ae2e7e2
latest_commit_time  = 2026-10-12T09:01:27Z / 2026-10-12 17:01:27 +08:00
review_date         = 2026-10-13 Asia/Singapore
previous_contract   = review_report_v45.md
reviewed_response   = response_v46.md
campaign            = V47_FTT_JOINT_TANGENT_DECISION
required_response   = response_v47.md
new_campaign_limit  = 28800 seconds
production_merge    = NOT_APPROVED
```

目标仍为0.7nm、周期单胞内任意非可分三维材料/几何、complex128 Nédélec H(curl)、双Floquet、Fourier-DtN、复E/H与衍射/体吸收，在十进制2e12 B整机内存、有系统余量、零swap/OOC下，单场必要准备至验收≤172800s。**本支尚无合格方案承担该交付，8h研究预算不是目标48h成绩。**只做神经；不转W0/W1、传统Maxwell PC、全口面、存储或主线工程，不修改其他支线。

## 1. 证据与重新判断

本次读取最新Response V46、summary当前段、原始隐藏试探、路线/资源与模型身份，检查ftt_core_training及完整矩实现，并比较上版review后4次提交。前版review本地全文与远端blob aad0ba271b8a1eff56cfc5162d084508252b3720一致；原task blob a0d3606aedbbce37066338de3763fe802590dedb及目录规则沿已读全文核对。目录无新增supplement或Review V46。未SSH、未查看实时进程、未在审阅端重跑M5或复算全部大型数组。

证据：[回执](response_v46.md)、[summary](outcomes/summary.md)、[隐藏试探](outcomes/records/hidden_updates_and_rounds_v46.json)、[路线与身份](outcomes/records/residual_branch_routes_v46.json)、[完整Gate](outcomes/records/full_numerical_gates_v46.json)、[成本](outcomes/records/resource_costs_v46.json)、[训练源码](../../src/solvers/ftt_core_training.py)、[矩映射](../../src/solvers/ftt_factored_moments.py)。上述源码按reviewed_HEAD解释；正式训练/验收source为0b8fb32fbf180b5dc775dac6642f27cd198afa60，不是发布HEAD。

| measured；M5/5nm/384hex/p3/N31968/完整40端口 | 学习修正 | 冻结修正 | 正式门 |
|---|---:|---:|---:|
| 原native/augmented残差 | 0.346345939530 | 0.346325842741 | 1e-6 |
| 散射E相对误差 | 0.0646210654522 | 0.0645635958293 | 1e-4 |
| 散射H/curl相对误差 | 0.0646528880296 | 0.0645954888578 | 1e-4 |
| 独立能量闭合 | 0.0227388903550 | 0.0227358257773 | 1e-5 |
| 新LSMR迭代/隐藏调用 | 21354/35 | 21340/0 | 不是精度 |
| 隐藏实际变化范数 | 5.47531795873e-7 | 0 | 不单独证明有效学习 |
| attempt秒/同时树采样峰B | 9139.93418654/935538688 | 9105.53692083/869515264 | 非冷启动 |
| actual/producer联合门 | FAIL/FAIL | FAIL/FAIL | 不挑有利输出 |

实际读出、MPC/端口、求积均通过，不能再用writer解释场误差。两条正常完成六轮，不是被资源或前端截断。学习路线核心求解约9018.23s，隐藏更新约15.48s；每条18个核心中14个仍未达到原内层诊断标准。有限子问题失败不是全部网络容量已耗尽的证明。

**这次的重点证据不是参数数量，而是隐藏更新实际发生了什么：**第1次隐藏更新loss由0.4799428122试探到1057256.2419，回退后为0.4799425477，参数步约2.99e-8；第3次由0.4709311550试探到4736978.5588，最后参数步约1.11e-9。源码每轮fresh L-BFGS，隐藏更新时输出层全部固定，tolerance_change=1e-9。记录未给出所有内部退出分支，因此不能认定某个容差就是唯一根因，也不能仅凭大loss认定梯度有bug。

明确修正此前决策的不足：单纯加宽、缩放或追加复制特征的修正网，没有充分处理“改变隐藏函数时，输出系数也需要配合改变”的耦合。V46新网复制原隐藏函数和x/y输出，仅z输出清零；冻结对照没有新的一维特征空间，主要扩展组合方式。其负结果不能推广成所有独立特征或所有大网络失败。另一方面，继续添加同类分支也已没有投入依据。

## 2. 为什么选择联合切线，而不是再换架构

旧流程每次只解一个输出核，然后固定全部输出，单独移动隐藏层。新流程在同一个局部模型中，允许修正网的三个核及隐藏函数一起移动，以检验能否避免破坏原有系数抵消关系。只学习输出的对照用于区分“联合线性代数有效”与“隐藏学习有增量”。**这是待证假设，不是宣称已找出唯一根因。**

本项目早期MLP已经试过GN，不能声称首次发现GN；本次不同点是当前FTT的全参数耦合切线、已合格的低存储矩收缩、严格真实试步和同态隐藏消融。若下述短验证不能给出可信下降步，就不启动长续算。相关依据限于机制：[SciPy非线性最小二乘](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)支持算子型雅可比；[Rathore等](https://arxiv.org/abs/2402.01868)研究残差优化的病态性，均不证明本Maxwell问题会成功。本轮不安装新库或复制其整套算法。

## 3. 起点：复用V46最终学习修正，不再生成第三网

从V46 run/index解析RESIDUAL_FTT_R8_LEARNED的**最终完整六轮**双网checkpoint，冻结PT SHA256/bytes和清单后才能运行。禁止猜测同名文件、挑best或重训补文件。必须匹配：

```text
correction_model_parameter_hash = 68960e7a840f84ef901edf1492946eff0f4a3918b638d5ba7025dac4b29d0a36
base_model_hash = 4d46260fe9668557393133dc9c93f737955ef4fda0a8f2562dcbf437f49c70f9
base_checkpoint_sha256 = 0121d04be3ae7c8fdaed1fefe23462c378dc81fa841ee0751040c7800d2b4978
fixed_g_array_hash = 9ee7039a391203426452e4bd45ca92aae2d48a55257d4acfa1febb609ccba528
native_sha256 = 2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215
moments_q30_sha256 = 22715fac468c4e3647e99672117f0f855dfe424914f9fce16be090a693f5
phase_sha256 = 32824e3063679681f77f6bb103fbb1ec9264f09f3441201407f6d0144cdc2ecc
```

模型hash不是PT文件hash，两者均须核对。继承修正6轮/18核/21354内层/35隐藏调用；原基网14轮前缀另记。base及c0/g不变；恢复实际c与r配对≤1e-10。两条新路线从逐位相同的状态分叉，新阻尼状态从下面合同建立，不冒称恢复旧LSMR内部状态或旧L-BFGS。

## 4. 数学合同：实参数、复残差、matrix-free联合更新

令theta为修正网参数，d(theta)为完整H(curl)插值。训练归一化沿V46的固定norm(g)，正式验收仍用原norm(f)。令realify(z)=[Re(z);Im(z)]，不额外乘sqrt(2)：

```math
e(\theta)=\operatorname{realify}\{[A d(\theta)-g]/\|g\|_2\},\qquad
\mathcal L=\tfrac12 e^T e,\qquad c=c_0+d(\theta).
```

每个parameter tensor采用父状态的固定尺度s=max(1,RMS(tensor))，构成正对角S；两路线共同输出部分尺度相同。尺度在全批冻结，不用参考或试探误差选择，不是V45的特征SVD放大。

```math
\mathcal J v=\operatorname{realify}\{A\,D d(\theta)[S v]/\|g\|_2\},\qquad
v_\lambda=\arg\min_v\left\|\begin{bmatrix}\mathcal J\\\sqrt\lambda I\end{bmatrix}v-
\begin{bmatrix}-e\\0\end{bmatrix}\right\|_2^2,\qquad
\theta_{trial}=\theta+S v_\lambda.
```

实际实现只提供JVP/VJP和增广LinearOperator，绝不形成J、J*J、N×P、全FE逆或新的全局因子。参数是实数，复残差必须正确实化；rmatvec使用实配对，不能照搬复输出系数K*当全参数雅可比。基网不参与任何导数。

完整FTT切线必须同时包含三项：

```math
D(XYZ)[v]=(DX[v])YZ+X(DY[v])Z+XY(DZ[v]).
```

一维核AD配合现有完整矩收缩；每项准确后备、Bloch相位、Piola、owner、MPC全部保留。不能沿用仅有一个活动核的DirectionField而漏掉另外两项。VJP可复用已合格mapping.vjp，随后按参数mask和S拉回；每次调用清理梯度，不把.grad缓冲当迭代状态。

采用小型显式阻尼GN控制器；优先复用仓库已有合适控制逻辑，不复制旧MLP/Gram路径。初态全参数J用seed4214701的实Rademacher向量做4次幂迭代，h为最后的非零Rayleigh估计，不称精确谱界；两路线使用同一h。lambda0=1e-3 h，允许范围[1e-12 h,1e8 h]。J作用严格为零时独立见证后标停滞，不用任意数凑通过。

每次增广LSMR：atol=btol=1e-6，conlim=1e12，maxiter=200，零初值；不做旧300+900补足。真实报告增广残差及normal-equation缺陷，内层达到上限仍可提交有效下降试步，但不得标精确子问题最优。

```math
pred=\tfrac12(\|e\|^2-\|e+\mathcal Jv\|^2),\qquad
ared=\mathcal L(\theta)-\mathcal L(\theta+Sv),\qquad \rho=ared/pred.
```

pred不包含阻尼。pred>0、ared>0、rho≥0.1才接受；rho>0.75时lambda除3，0.1≤rho<0.25时乘2，其余接受时不变；拒绝乘10，均受上述界约束。拒绝恢复全部参数/buffers/cache/c/r。不能将旧“有限更新必须与线性预测相等1e-10”照搬到非线性联合步；1e-10只要求实际模型与独立实际映射一致。

LSMR方向无有限正pred时，允许一次同lambda的Cauchy后备：q=J^T e，v=−alpha q，alpha=(q^T q)/(norm(Jq)^2+lambda*q^T q)。仍需真实接受；不扫描优化器。连续8次拒绝或lambda上界无下降时保存真实负结果，不无限重启。

## 5. 资格、短试步与两条真正的数值路线

A：小型复数乘积网络上，全部参数JVP/实伴随、隐藏/输出mask、增广LS与独立小SVD、pred/ared、拒绝恢复均须通过。真实父状态至少3个非零方向覆盖隐藏、输出和混合；JVP对独立原点值差分稳定段≤1e-5，实伴随≤1e-10，vjp与现有原梯度≤1e-9，单活动输出退化到旧K配对≤1e-10。分别检查phase和base冻结。无需重跑旧全量qualification或benchmark。

计时一次JVP、VJP、真实试步及保存，报告合计而非热核。随后在同一父状态作至多3个阻尼试步、总LSMR≤400、wall≤900s的无标签探针；按固定接受规则得到稳定实际下降步，且探针累计原native残差相对下降至少1e-3、超过独立重复评价漂移的10倍，才准入B。这是本批投入门，不是物理精度门或方法不可能证明。探针结束恢复父状态，两条B均从原同态开始；探针费用保留，不能挑探针最优点warm start。若没有下降，保存pred/ared/原残差与导数质量，关闭本机制，不再启动数小时旧算法。

| B路线 | 真正可更新参数 | 解释 |
|---|---:|---|
| FTT_JOINT_LM_ALL | 修正网全部19200实参数 | 三轴输出和3360隐藏参数联合 |
| FTT_JOINT_LM_OUTPUT_ONLY | 修正网15840输出实参数 | 同态隐藏固定；三轴输出仍联合 |

基网19200参数全冻结；总持有38400不变，无第三网、无增rank/宽度/层数/载波。冻结控制也继承神经训练，不叫传统零训练基线。两条各≤5400s、32次真实非线性试探、16次接受、4800计费LSMR迭代，取先到者。谱估计/探针/拒绝/检查/丢失工作全部计费。普通bug修复后继续，未收敛不伪装为bug。

前3个接受联合步另外记录仅隐藏变化、仅输出变化的实际loss（纯诊断，不作为候选选择）；用它核查两类更新是否确实需要配合，不能仅凭小参数范数讲故事。每4个接受步及终态，隔离评分合成场的原R/E/H；不把参考向量或误差图反馈求解。完整原残差到1e-8立即联合验收。若原方程未达门但更新小，记停滞，不授PASS。

每个接受点保存base/correction模型、S、lambda/h、实际c/r/g、参数mask、RNG及预算；下次线性化使用新参数，拒绝则可复用旧切线。不声称未保存的LSMR内态可恢复。控制自身失败不取消另一条或终态验收；不重跑V46旧六轮作第三条长对照。

## 6. 数值门、成本门与0.7nm关系

| actual双网与producer分别评分 | 不变门限 |
|---|---:|
| native/augmented/独立total原残差，使用原载荷 | 各1e-6 |
| total/scattered E/H/curl、六点、四类完整40复通道 | 各1e-4 |
| R/T/A/A_volume、独立吸收一致性及能量闭合 | 1e-5 |
| 每衍射级功率差 | 1e-6 |
| 实际双网重建、MPC/端口恢复 | 1e-10 |
| 网络q30/q60及原A作用、FE独立积分 | 1e-8 |

用旧逐点双网求和后的完整矩独立验收，不用联合JVP与自己互证。原p3参考只读，不重求。不得通过新分母、误差相位拟合、放宽求积或老师解覆盖输出造PASS。残差未过的R/T/A仍diagnostic；既有reference/validation用途标记完整继承，不称盲测。

正式PASS以全门为准。仅在原R≤1e-3且散射E/H各≤1e-3时记强研究信号，仍不授生产资格。只有原残差下降而场停在百分之几，不支持再开同类长期训练。若ALL不优于OUTPUT_ONLY，就没有新隐藏学习净收益；比较共同工作量与真实费用，不按不等精度授20%资源收益。

冷单场前缀至少包括原基网12788.395328277858s与本次所依赖的V46学习9139.93418654s，合计约21928.3295148s；另有必要准备/检查，缺项仍UNKNOWN。不能把这6.09h从新候选费用中删除，也不能机械加入无关旧研发。小模型的准确解与原尺寸生产可行性分别判断。

只有ALL在M5联合PASS、控制已验收、安全且总窗余量≥7200s，才按旧合格定义运行一次0.7nm几何×0.14缩小非可分pilot（≤5400s，余1800s交付）。材料/模式/背景/chi/网格/参考重绑定；不得直接迁移参考系数或硬套40端口。该缩放几乎保持电尺寸，不是原尺寸高频能力；后续仍须扩大电尺寸、精度资格及实测容量模型，不得直接上原50×25×140nm模型。

**最终目标的近期交付不能依赖此未通过支线。**2TB只放宽容量，不会补救目前原残差和场精度；主项目的可扩展迭代架构由主线处理，本支不接管。若本轮无强信号，结论为CLOSE_CURRENT_FTT_SOLVER_FAMILY / NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE；不自动以另一个网络/优化器名字续命，也不扩大为所有NN不可能的数学结论。

## 7. 连续执行、预算、提交与精简交付

新唯一窗口28800s：实现/资格/探针软7200s，两正式路线各硬5400s，最终至少1800s验收发布；未用软额度可以登记调配，不增加总窗或单路线硬额度。普通API/schema/复数/mask/缓存/保存错误同批最小修复、targeted复验并恢复健康边界，无bug次数交棒卡。安全、ABI、不可恢复身份和成本出口不绕过；不full pytest、不重装、不重复健康参考/基场/网页。

保持CPU-only、MPI1、math/Torch intra/inter1、一个现场合格物理核；numeric warn12/hard16GiB，临时规划≤12GiB，新增cache/AD≤1GiB，轻2GiB，ownswap/OOC0，原PSI/SMT、系统max(128GiB,10%)及384GiB邻增长保护不变。持久launcher/watchdog、150s收口及120s保存沿用。新全参数J不能构建全网格AD图或64000×19200矩阵；清楚记现有O(N)场/算子/端口成本。

先只读核对branch/HEAD/worktree/锁/PID/start_ticks与已有V47；运行中不改源码、不kill或启动副本。无活跃run且clean时精确fetch/ff-only。分歧只涉及本review且无数值冲突时，沿既有同分支普通merge许可保留历史；不reset/stash/rebase/amend/强推/merge master。重复指令不重开预算。

实现进入通用solvers模块，尽量复用旧检查点、残差上下文及GN控制；不复制整套按版本编号的数值训练器。先最小tests/validate和clean实现commit，再串行执行：

```text
input/task042extra_feinn_5nm/v47_joint_tangent_checks.dat
input/task042extra_feinn_5nm/v47_joint_step_probe.dat
input/task042extra_feinn_5nm/v47_joint_all.dat
input/task042extra_feinn_5nm/v47_joint_output_only.dat
input/task042extra_feinn_5nm/v47_joint_compare.dat
```

```bash
python scripts/launch_task42extra_durable.py input/task042extra_feinn_5nm/<one-run>.dat
```

wrapper选择本任务合格activation并调用scripts/run_case.py，逐项清场。每run保留原one-dat provenance、physical/input/source/environment/hash；父模型/PT、mask/S、g、实际试探/接受/拒绝另外绑定。

提交顺序：C1最小实现/输入/资格；C2真实两路线与独立Gate；C3精简回执/summary/总账。response_v47.md主文≤120行，新增紧凑records覆盖parent、JVP/VJP、probe、pred/ared、共同控制、全门、成本与修复；大型轨迹留ignored，不再在多个JSON反复嵌套复制。更新本分支progress/模型总账/tests，历史全部保留。最终必须回答联合步是否有效、隐藏是否真有增量、M5是否过门、费用是否值得；不以代码/测试数量作进展。

数值完成优先发布，不为多页截图或自引用收据拖延；按仓库要求有限检查关键页，未见内容写NOT_VERIFIED，不虚称视觉PASS。审阅端只做源文和小型代数核验，不授工作站数值资格。只推本分支，完整有界包或硬出口后交准确HEAD、tracking/ahead-behind、clean及自身清场；未过本轮去留门则停止上述求解族，不自动开V48。
