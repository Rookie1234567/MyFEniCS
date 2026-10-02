# Review V10：关闭原样 GN 续跑，诊断参数尺度并有条件比较分组阻尼

## 0. 决定、身份与本批要消除的 blocker

**接受 V10 的等价导数加速、完整状态保全和独立验算；不授予神经求解、生产或合并资格。关闭继续原样延长 plain/phase GN、重复监督拟合以及追加缓存微优化。下一批先在唯一冻结的无标签 phase 状态上诊断参数尺度、阻尼与两种残差梯度的关系；有预登记支持证据后，自动完成一个同起点、同预算的“原阻尼／固定八组曲率阻尼”对照及独立验收。工程问题可有据修复，资源压力不可绕过。**

本批对应 blocker：网络参数更新已经更便宜，内层线性系统也经常达到规定精度，但真实 Maxwell 方程仍未满足。要判断原始参数坐标下的步长度量是否造成无效的小步或不可靠的大步，不能再把“提高吞吐量”当作足够的求解方案。参数尺度尚不是已证明的唯一根因；本批是有界假设检验，而非通用生产预条件器研发。

```text
repository                 = Rookie1234567/MyFEniCS
execution_branch           = task42extra_feinn_5nm
worktree                   = /home/fenics/Projects/NN-Lab-V2
review_date                = 2026-10-02
reviewed_HEAD              = c35fb5714e81736a5fe5e4f90159f4dacaf4b2a9
latest_commit              = docs(task42extra): close V10 costs and record actual rendered-view blocker
latest_commit_UTC          = 2026-10-02T06:22:34Z
original_base_SHA          = fbac3d8777fcfd897d93b898cb9f460f79ddd6ff
previous_review            = review_report_v9.md @ 47317bb648d5e2237657f8b6c75c239ab5bf55c5
response_reviewed          = response_v10.md
next_batch                 = V11_PHASE_PARAMETER_METRIC_DIAGNOSTIC_AND_PAIRED_PILOT
response_required          = response_v11.md
new_batch_budget_seconds   = 21600
production_merge           = NOT_APPROVED
```

最终目标仍是约 2 TB 整机物理内存内、0.7 nm、周期单胞内任意非可分三维 Maxwell 的准确稳定计算。本批只研究原 5 nm M5/p3 方程，不是目标尺寸、连续精度或 48h 资格。小型 p5 direct reference 与本批允许的研究用 Gram factor 不能代替分布式、matrix-free、可扩展 Full3D iterative 主线。

审阅读取了远程分支、任务目录、最新 response/summary、GN 续算、内层摘要/逐试探 CSV、运行与资源索引、当前 GN 源码及前一 review 后的 11 个提交。原 task、目录规则和未改动历史以当前 blob 与已读全文对应；上一 review 本地完整副本的 Git blob 与远程一致。未 SSH 重跑、未访问工作站 ignored 大数组；本文 measured 来自已提交证据，下一批均 not_run。本地合成代数验证不等于 M5 实测。

先读根/目录 AGENTS、[仓库原则](../repository_work_principles.md)、[task](task.md)、历次 review、[Response V10](response_v10.md)及本报告。**本报告仅覆盖旧合同对参数步长度量变更的禁止，授权下述唯一固定分组方案和对照；不修改旧 task/review、失败结果和数据血缘。**

## 1. V10 审查结论：工程收益成立，求解仍未合格

依据：[导数复用](outcomes/derivative_reuse_v10.md)、[完整续算](outcomes/cached_gn_v10.md)、[内层摘要](outcomes/records/inner_summary_v10.json)、[逐试探](outcomes/records/accepted_steps_v10.csv)、[最终资源账](outcomes/records/resource_costs_v10.json)。下表无量纲，场误差相对原 V1 同 p3 参考，功率误差归一于入射功率。

| measured 指标 | V10 plain 无标签终态 | V10 phase 无标签保全态 | 严格门限 |
|---|---:|---:|---|
| native / augmented | 1.01543479754 | 0.978821198632 | 各 1e-6 |
| 散射 E L2 相对误差 | 0.998888499958 | 0.362017880269 | 1e-4 |
| 散射 scaled-curl / H 相对误差 | 0.998905944861 | 0.362633734179 | 1e-4 |
| G 场相对误差 | 0.998905515120 | 0.362618575540 | 不能代替独立场/方程 Gate |
| 独立能量闭合绝对差 | 0.415935474681 | 0.0927477482932 | 1e-5 |
| 新增完整接受步 / 累计步 | 14 / 43 | 21 / 75 | 不是精度指标 |
| 完成内层 CG 的迭代中位数 | 68 | 28 | 不是 outer 数 |
| 完成内层真残差中位数 | 0.00955283 | 0.00833871 | 内层目标 0.01，不是 Maxwell 残差 |

四个固定态的“建立缓存＋完整梯度＋16次K＋释放”加速为 1.4614/1.5433/1.5299/1.5718 倍，完整 proposal 配对通过。接受 `EXACT_DERIVATIVE_ACCELERATION_PASS`，但不将微基准比例当作整个求解端到端加速。数值缓存约 1.10 GiB，建立、失效与释放费用保留；本批复用已合格实现，不再重跑四态长基准。

plain 场误差几乎不变；phase 从 V9 的约 43.7% 改善到约 36.2%，但用了追加时间且遭遇资源中断，没有达到联合研究信号。phase 两次停止均由系统 memory PSI 触发，自身 swap 为零，压力来源未确定。分别保留 `termination_reason` 与 `retained_state_numerical_status`：不能把 `PDE_OPTIMIZATION_NEGATIVE` 直接解释为完成全部预算后的失败，更不能写成 OOM、网络不可表达或 PC 已无效。

监督 phase 的 E_G/L2/curl 为 0.010022747742/0.009557925207/0.010034208799；G/curl 仍高于 1% 的联合门限，不能舍入判通过。**不再专门追加一轮监督训练去跨过 1%：这不是当前原方程求解的主要验收目标。**

逐试探 CSV 显示多个低阻尼步被拒、高阻尼步接受且改进很小的循环；有些接受步的 native 不降。它支持检查局部模型、尺度与残差度量之间的关系，但不能据此断言只需减小阻尼或增加 CG 迭代。

p5 参考及 p4/p5 的已审结果保持：散射 E 差约 2.1591e-4、curl 差约 1.17945e-3，仍有 H/区域敏感性和未验证的 h/端口截断误差。**本批不追加 p6、细化网格、增加端口或重求任何参考。**

## 2. 计算范围、数据身份和自主处理

只采用 V10 **无标签 phase、第75完整接受边界**，不得改用更好的 V8 标签拟合、V10-D、历史 best 或 last_trial。文件路径从 [V10 索引](outcomes/records/run_index_v10.json)读取并逐字节核对。

| 冻结对象 | SHA256 / 明确含义 |
|---|---|
| phase C durable PT | cf6919a8ee86e32ad7f0f4b0d4ef8411061b149c564dd289237334f90b7d9e86 |
| phase C 冻结 NPZ 视图 | 4b538b3f785902de369d5a0602b5d3267a08cc34fa8e68ab509ebc51c2652917 |
| 参数/保全 source | 5cda1c3995633c4f6c86f4b47d3163efb1cdc8c6 |
| 独立 NPZ export source | ca0c48a96ef555f5b64c5fff17ea8ed5e13e17ef；不是参数训练 source |
| p3 native | 2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215 |
| p3 Gram | 2c984449248c02f01f4a41a681d00015bbe779add0ef30f0141d9eccf75b01c9 |
| q15 完整矩 | 0260c986bc7a71d6b8d6b0b695df4ca730d24654f5ad0705313a45205c28b69e |
| 同 p3 准确参考，只在最终验收读 | 0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7 |
| Si 材料表 | 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2 |

固定 5 nm、原 Si/air 非可分缺口、384 hex/h1.25nm、N1curl p3、31968独立复FE、40端口、grazing1°/phi0/s、双Floquet/Fourier-DtN、体和端口q15、FP64/complex128。网络仍为3→64→64→64→6的单入射相位网络，8966实参数，完整边/面/内部矩。载波、背景、材料、归一化与积分不变。

```text
A：唯一状态/压力证据 → 无标签尺度与方向诊断
B：固定分组度量的最小实现/数学资格
A有支持证据且B通过 → C：同起点 phase-I 与 phase-block 两路线短对照
E：独立验收、共同工作/时间比较、下一步分流
```

A/B 可推进各自独立的代码和小测试，但数值工作串行。A 不支持尺度假设时交付否定结果和 B 的轻测试，不强行跑 C。可定位工程错误最多3次有改动/测试证据的重试；每条 C 最多1次完整状态故障恢复，全部耗时和计数继承。正常停滞不是 bug；不靠改精度、重置状态或原样重启解决。

索引缺失先从本任务原 manifest/hash 副本恢复，禁止扫描或修改其他项目。PT/NPZ 不匹配则仅做不依赖它的工作，不拿参数-only或猜测mu代替完整身份。不得重新执行旧 Adam、旧 GN、旧监督前缀来补历史。

## 3. A：诊断原始参数尺度、阻尼及梯度关系

### 3.1 为什么做、哪些量保持不变

原参数中“权重改变0.01”和“偏置改变0.01”可能对电场产生很不同的影响。原阻尼把所有参数步长用同一种欧氏尺度约束；本批检查是否存在明显不均衡。V2调整过的是**独立FE系数**，本批检查的是**网络权重/偏置的步长度量**，两者不是同一个变量空间。

固定原 Riesz 目标及 GN 曲率：

```math
r=Ac(\theta)-f,\quad d_G=f^*G^{-1}f,\quad
L_D=\frac{r^*G^{-1}r}{2d_G},\quad
g_D=\frac{\mathrm{Re}(J^*A^*G^{-1}r)}{d_G},\quad
Kv=\frac{\mathrm{Re}(J^*A^*G^{-1}AJv)}{d_G}.
```

同时只计算一次用于诊断的原欧氏残差梯度：

```math
L_E=\frac{r^*r}{2f^*f},\qquad
g_E=\frac{\mathrm{Re}(J^*A^*r)}{f^*f},\qquad
\gamma=\frac{g_E^Tg_D}{\|g_E\|_2\|g_D\|_2}.
```

若 gamma<0，则 -g_D 对 L_E 的一阶变化为正；若 gamma>0，也不保证有限步同时下降。它是此状态的局部诊断，不是全局结论；不能用该量擅自换 loss 或混合权重。零梯度单列，不填一个假的cosine。

### 3.2 固定八组曲率估计

按已记录的 parameter_order 将四个 Linear 层的 W、b 分成八组，大小192/64/4096/64/4096/64/384/6，总8966。全部组参与更新，不能冻结 hidden 或附加FE自由参数。

每组用 seed=4211101 的3个独立 Rademacher 单位方向；方向只支撑本组，每个非零分量为正负1/sqrt(n_group)，随机生成顺序按层W、b固定。计算24次 K 作用：

```math
q_{\ell j}=v_{\ell j}^TKv_{\ell j},\qquad
\widehat h_\ell=\frac13\sum_{j=1}^3q_{\ell j},\qquad
\bar h=\frac{\sum_\ell n_\ell\widehat h_\ell}{8966}.
```

这仅估计各组平均方向曲率，**不是逐参数精确对角、完整条件数或谱界**。保留全部q、离散程度、K向量范数和负曲率舍入判据。明显负值或不有限应定位接口/数值错误；仅可把满足256 eps乘操作尺度的微小负舍入归零并记录。bar h须严格正且有限。

构造唯一、固定、不扫描的尺度：

```math
m_\ell=\min(10^4,\max(10^{-4},\widehat h_\ell/\bar h)),\qquad
M=\mathrm{diag}(m_\ell I_{n_\ell}),\qquad S=M^{-1/2}.
```

M只有8个不同正值；可展开为8966个FP64数，不能构造大稠密矩阵。记录clipping数量/原因/幅度，不能省掉零曲率组；整轮固定同一M，不按结果重新估计、挑探针或修改上下界。

### 3.3 最多四个真实试探，只做观察

固定theta0、原PT的mu0/h0与缓存。记录各组参数/梯度RMS、饱和激活比例（只读缓存）、mu0/(方向曲率+mu0)，以及下述方向在各组的步长。A新增K总数≤32，完整真实目标试探≤4，实际数值子阶段≤1200s（含加载、fresh G、缓存、存盘）；全A含只读压力/原记录≤1800s。

取 d_I=g_D、d_M=M^{-1}g_D，分别计算 Kd 并令：

```math
\alpha_X=\frac{g_D^Td_X}{d_X^TKd_X+\mu_0d_X^TXd_X},\qquad
s_X=-\alpha_Xd_X,\qquad X\in\{I,M\}.
```

分母不正或方向非下降时记录并停止该试探，不人为绝对值修复。分别评价theta0+s_X和theta0+0.1s_X，共至多四次；记录原L_D、native/augmented、pred/ared、g_E的方向预测。随后完整恢复theta0及缓存版本。**不提交参数更新、不用四个试探中最好的点作C初值；不读参考场。**

C的预登记启动信号仅为研究筛选：身份/导数/资源均合格，存在至少10倍的组曲率跨度（分母使用1e-4 bar h的固定下限），且两个M试探至少一个使L_D实际下降并使native不超过theta0的1.01倍。通过只说明值得花一次短对照，不能称尺度根因已证实。未通过记 `BLOCK_METRIC_PILOT_NOT_ADMITTED`，仍交付所有诊断和可完成的B/E，不启动另一套loss/缩放扫描。

## 4. B：一个固定参数度量，两种不同的数学关系必须分清

参数缩放能改变信赖域各方向的步长，相关思想见 [SciPy least_squares 的 x_scale 说明](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html)。这里只借鉴变量尺度原则，**不升级SciPy/Torch，不直接调用新的黑箱优化器；八组随机曲率方案是本review预登记的研究设计，不是文献已证明适用于本模型的结论。**

### 4.1 新方案真正改变什么

候选仍最小化原L_D，采用：

```math
(K+\mu M)s=-g_D,\qquad
(SKS+\mu I)y=-Sg_D,\qquad s=Sy.
```

这改变了阻尼对不同参数方向的限制，是**优化算法改动**，不是V10那种严格等价的缓存加速；不把mu M加到正式loss里。M固定，故没有额外的参数依赖导数。实际网络参数仍为theta，所有原方程验算都用c(theta)。

单纯把旧方程换坐标则是另一条式子：

```math
(K+\mu I)s=-g_D
\quad\Longleftrightarrow\quad
(SKS+\mu S^2)y=-Sg_D,\qquad s=Sy.
```

**禁止混淆两者。** 前者用于新度量候选；后者只用于小型代数测试，证明实现没有错误地把缩放与改变阻尼混为一谈。原FE空间、G、A、f、连续方程都不变。

### 4.2 最小资格，不再追求整条非线性轨迹逐位相同

复用V10缓存/矩/JVP/VJP资格；新增src/solvers中的小型度量适配器，runner只编排。相同theta缓存不按y对象地址判身份。检查S=I回归、八组顺序、共轭与实梯度、原物理参数空间的残差、接受/拒绝回滚及可恢复schema。

小型非Hermitian复A、复J和HPD G形成的实K模型，与独立稠密解分别验证上述两种等价关系，操作相对差≤1e-10。覆盖不同尺度、近秩亏、mu>0、拒绝试探和方向回写。真实M5检查g_y=Sg、K_yv=SK(Sv)与直接链式作用≤1e-9，3个非零实方向差分稳定区≤1e-5；S=I短proposal与旧实现在数值容差内一致。新增真实B资格≤96次K，全部费用计入B。

不要求不同度量的proposal相同；也不为近阈值浮点分岔反复修到长GN轨迹逐位相同。充分预算下S=I数值不一致才是实现问题。总B（代码定向tests、真实资格、修复）≤5400s，不重跑旧四态性能基准、不full pytest。

## 5. C：唯一一对 phase 路线，从同一theta0开始

A启动信号成立且B通过后，无需再请示，串行完成：

| 路线 | 正式目标 | 步长度量 | 起点 |
|---|---|---|---|
| V11-PHASE-IDENTITY-METRIC-CONTROL | 原L_D | I | 唯一V10 phase75无标签状态 |
| V11-PHASE-BLOCK-METRIC | 原L_D | A中冻结的M | 完全相同theta0/buffers/mu0/h0 |

这是同状态的**两个独立研究分叉**，不是把一条结果warm start给另一条。原累计75步和完整历史成本记录为继承值，新增步单列。S和M属于新schema，不能把变换后的优化状态伪装成旧V10可直接续算的状态。

两条均保留相同原mu0/h0和原阻尼接受规则：最多8次阻尼试探；真实ared>0、eta≥0.1才接受；eta>0.75时mu/3，eta<0.25时mu×2，拒绝mu×10，夹于[1e-12 h0,1e6 h0]。预测下降始终是 -g_D^Ts-0.5s^TKs，不加入阻尼项。

**两条都不新建range/Ritz或其他PC**，旧phase75应确认没有已建PC。若身份显示存在PC而与记录冲突，先解决冲突，不静默丢弃。关闭本对照的自动PC后备是双方共同限制，不能把control称为与旧整条策略完全相同；唯一组间差异是M。全参数更新，不回冻结末层、FE变量优化或监督拟合。

内层CG最多40步。变换后的相对残差和原参数方程残差均记录：

```math
\rho_{\theta}=\frac{\|(K+\mu X)s+g_D\|_2}{\|g_D\|_2},
\qquad X=I\ \mathrm{or}\ M.
```

只有真实rho_theta≤0.01才称内层converged，不能只看缩放坐标残差。达到40步仍可按原规则验证有限下降方向，不以inexact自动停整批。未取得方向时，control用原Cauchy，候选用d=M^{-1}g_D的Cauchy方向；步长(g_D^Td)/(d^TKd)，仅试1/0.5/0.25，并通过同一真实目标接受。所有分支计数和原参数更新保存。

每条新增≤5400s、30接受步、1200 K、2500 JVP+VJP、128真实试探，取先到者，含fresh G/缓存、失败恢复及保存。每条只一个实际目标，不扫M、探针、mu初值或网络。A的公共诊断成本单列，两边比较同时报告包含公共准备的从本轮起算成本。

每个接受步持久保存theta、原参数顺序/buffers、mu/h0、度量及hash、RNG、计数/预算。每步记录原native和augmented（可限制仅必要原action）；全field在E统一算。至少固定保留0/30/60/90分钟之前最近完整状态（有实际边界才记录）与最终态，未到者not_run；不按参考误差选择best。预算末端仍按V10允许的安全提前CG返回及验证处理，不能因新度量禁用watchdog。

标签始终：reference_used_for_training=false、features_reference_exposed=false、pde_only_solve=true、benchmark_previously_seen=true、production_initialization_allowed=false。A/B/C白名单不含参考场、D权重、Phi/Q或p4/p5标签。E冻结后才读原p3参考；本轮没有新的D监督训练。

## 6. E：同时检验方程、场和成本，而不是再看一条loss曲线

实际终态冻结后，独立ML重建q15/q30，独立FE compare-only复用V1参考。保留total/scattered E/H/curl、六点复场、四类40级复通道及分母、逐级功率、R/T/A_balance/A_volume/R00_s/p/total和原材料/界面区域。拒绝只输出近似云图或能量和。

严格Gate不变：native/augmented/原total≤1e-6，场与完整复通道≤1e-4，功率/能量≤1e-5，每级功率≤1e-6，MPC/恢复≤1e-10，q15/q30≤1e-8。相对分母与近零规则仍沿原合同，不拟合全局相位。原方程未通过的功率全部diagnostic。

从两边同一工作量/共同时间前最近完整状态比较，记录实际间隔，不插值造场。完整接受步、K/原A/AH/Gsolve、CG、拒绝次数、各组实际更新、mu归一化贡献和全过程RSS/wall一起报告。度量候选自己的准备成本不能藏掉；如果PSI影响不同，标 `PERFORMANCE_INCOMPARABLE_RESOURCE_WINDOW`，不宣称同成本胜出。

| 研究结论 | 预登记标准或边界 |
|---|---|
| PARAMETER_METRIC_INTERFACE_PASS | 数学/回写/事务资格通过；不是物理解 |
| BLOCK_METRIC_PILOT_NOT_ADMITTED | A未支持或安全窗口缺失；不是FEINN普遍无效 |
| BLOCK_METRIC_RESEARCH_SIGNAL | 度量候选native/augmented都≤0.1倍theta0（约0.09788212），且都≤0.5倍control；散射L2/curl均≤0.1且优于control；完整成本披露。只说明该pilot值得继续，不是严格通过 |
| PDE_SAME_DISCRETE_PASS | 对应无标签路线全部原严格Gate合格；仅本M5/p3，不授予网格/生产/0.7nm资格 |
| NO_USEFUL_METRIC_GAIN | 只是loss更低、内层更快或几个百分点的局部改善，未满足联合研究信号；停止同类组尺度/阻尼续扫 |
| RESOURCE_STOP / ENGINEERING_BLOCKED | 实际停止原因与保存态数值分别报告，不强行当完整时长负结果 |

若新度量有界对照仍无实质改善，下一次review应转向不同表示/弱残差或问题结构设计，**本批不自动切换这些方案**。不继续给同一GN组合追加第三轮运行，不自动启动多载波、p6、h细化或目标尺寸。

## 7. 资源压力：先取得可信窗口，不降低保护来凑完成

V10已出现两次memory PSI停止。PSI反映资源压力造成的停顿，不等于本任务发生swap或OOM，见[Linux PSI说明](https://docs.kernel.org/accounting/psi.html)。本批先只读提取旧两次触发的时间、some/full/窗口/阈值、MemAvailable和自身RSS/swap；来源未知就保留unknown，不归罪其他项目。

每次新数值启动前，按**当前已经批准的watchdog阈值**做至少60s短时稳定性观察，同时满足原MemAvailable/邻增长/CPU资格；记录实际阈值，不人为放宽PSI以继续运行。窗口不合格则交付代码/轻测试及准确blocker，不无限等待或自动轮询抢跑。系统压力恢复重试仅允许本批最多一次，且必须重新通过相同稳定性检查、继承费用和完整状态；再触发则结束受影响数值链。纯工程修复不授权重启仍活跃的作业。

CPU-only、MPI1、数学/Torch线程1，现场空闲物理核；数值warn12/hard16GiB、factor内部规划12GiB、新detached缓存≤2GiB（总树仍受16GiB），轻tests/浏览器≤2GiB，自身swap/OOC0。系统余量=max(128GiB,10%effective total)，加至少384GiB邻增长及本任务预算；disk≥50GiB，原artifact容量检查保留。M/探针不应产生大矩阵；不调整全局库、交换空间、其他项目锁/亲和性/进程。

复用durable launcher＋watchdog＋worker，150s前停止新增工作并保留至少120s保存；A短探针同样留收口。每个进程持有的G因子销毁后才进入下一数值阶段，保存模型不包含因子或激活图。独立stage重复setup和恢复fresh setup全部计费，不能称零成本复用。

## 8. 新增预算、Git、提交和证据

本批新增总上限21600s（6h），不叠加旧未用预算。V10最终累计137403.03555569297s及原失联3284s/所有失败重放费用完整保留；现场补实际尾段，不清零。历史共同前缀在两条逻辑路线各归属一次，在全项目账只计一次。

| 子包 | 上限，包括正式计算与有界辅助 |
|---|---:|
| A：压力/状态/无标签诊断 | 1800s，其中数值诊断≤1200s、K≤32、真实试探≤4 |
| B：度量实现/定向数学资格/修复 | 5400s，新增真实资格K≤96 |
| C：唯一短对照 | 合计10800s，每条≤5400s |
| E：独立验收/compact证据/文档辅助 | 3600s，始终预留至少1200s |

未用额度可预登记转给既有工程修复，不增加C单路线限额、重复次数或未授权数学方案。需要改变物理、目标、环境ABI或安全规则不属于本批自主修复。文档渲染服务失败不阻塞独立数值工作，最多两次关键页尝试，真实阻塞保留。

实现前读对应src子目录AGENTS；数值适配器放src/solvers，复用cached GN与原compare框架，不复制一套大训练器。仅新增opt-in metric配置及状态schema，不改变ordinary default。先clean实现commit再运行，运行source与后续文档HEAD分开；新run/attempt/index不覆盖V1–V10。

建议提交：C1压力/身份/诊断与预登记；C2度量适配器/targeted tests；C3满足条件后短对照；C4独立比较及Response V11。不中途改活跃run的tracked HEAD，不amend/强推，不merge master或其他任务。

实现并资格化后，使用以下独立one-run输入：

```text
input/task042extra_feinn_5nm/v11_parameter_scale_diagnostic.dat
input/task042extra_feinn_5nm/v11_parameter_metric_checks.dat
input/task042extra_feinn_5nm/v11_phase_identity_metric.dat
input/task042extra_feinn_5nm/v11_phase_block_metric.dat
input/task042extra_feinn_5nm/v11_metric_reconstruct.dat
input/task042extra_feinn_5nm/v11_metric_compare.dat
```

各阶段仍由 `python scripts/launch_task42extra_durable.py <one-run.dat>` 选择合格FE/ML activation并调用 `python scripts/run_case.py <one-run.dat>`，先扩展白名单，不用旧输入冒充新case。串行确认清场再下一项，不能在shell中并发启动全部命令。不full pytest、不重装环境、不让FE顶层import Torch。

至少新增 `response_v11.md`、`outcomes/parameter_metric_v11.md` 和compact records：`campaign_design_v11.json`、`pressure_and_state_v11.json`、`parameter_scale_v11.json`、`metric_checks_v11.json`、`metric_trials_v11.csv`、`metric_comparison_v11.csv`、`repair_log_v11.json`、`run_index_v11.json`、`resource_costs_v11.json`、`gate_decisions_v11.json`。原始完整history留ignored并绑hash；建议每个新JSON≤200KiB，不重复嵌套全量history。

summary页首追加当前导航，保留旧结果；同步development_progress、development_model_registry、test_summary与changed_files。所有正式run保留input_original、resolved、manifest、input/physical/source hash、环境/材料/网格/模式、参数/度量/cache/标签/资源身份。报告哪些根因实际修复、A是否支持、C是否执行、真实方向和场有无改善以及准确性未决项。

仅推送 `HEAD:refs/heads/task42extra_feinn_5nm`。交付准确HEAD、显式tracking/ahead-behind、clean和自身清场状态后等待review。原Review V9页首对更早提交描述/UTC有小偏差：该旧结果SHA的实际消息与时间是 `docs(task42extra): bind V9 actual rendered view and final resource ledger`、2026-10-01T09:49:06Z；旧文件不改，本报告与新run以实际Git对象为准。
