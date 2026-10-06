# Review V53：补齐独立审核，以同模式h分辨推进0.7 nm完整三维场

## 0. 决定、身份与要消除的blocker

**V54有三份实际完整有限方程解、两项通过的有限模式增量和真实raw张量复用；没有NN收益，也没有完整NOTCH准确性。最终新进程审核因资源准入未完成，不能把actor内PASS升级为最终交付PASS。授权V55先消费保存状态补齐独立审核，再以固定828模式完成Z4/p7的h对照；预算允许时完成一项独立的p6横向h对照。停止继续盲增模式，不重新训练NN，不另起求解器或组件研究。**

本批消除两个具体blocker：已算出的科学状态缺最后独立消费；同模式下p6/p7仍相差约3.41%，高阶解的空间分辨资格不足。不得只补文档便停止，也不得越过真实原式、身份或资源错误硬跑。目标是新完整场及有决策意义的分辨证据，不是测试数量。

```text
repository             = Rookie1234567/MyFEniCS
branch                 = task42_neural_coarse_inverse
canonical_worktree     = /home/fenics/Projects/NN-Lab
review_date            = 2026-10-06
reviewed_HEAD          = c9efe49ec0b2605caf3e6790bdc70c83dfc3a14f
reviewed_commit_UTC    = 2026-10-06T11:54:12Z
latest_response        = response_v54.md
previous_review        = review_report_v52.md
previous_review_commit = bcc059f63478b468dff29a8a70d69a5710f2ca4d
original_base_SHA      = ccd357885f7f9be84efe3be07868cc94f13d93fc
sibling_readonly       = task42extra_feinn_5nm @ 8d617d4d206b08f38279320b67188db1b8ccd301
sibling_contract       = Review V29 / V30_ADAPTIVE_WAVE_NEURAL_GALERKIN
next_batch             = V55_AUDIT_COMPLETION_AND_SPATIAL_RESOLUTION
required_response      = response_v55.md
NN_training/inference  = NOT_AUTHORIZED_THIS_BATCH
merge                  = NOT_APPROVED
```

本Review回应已交付V54，新增V53；覆盖旧禁止Z4/p7与横向case、80000行上限及32/40/48GiB研究配额，只限本报告指定的新有限问题。旧结果、窗口、输入和FAIL均不回写，普通默认不变。最终目标仍是原50×25nm周期、z=−10..130nm、0.7nm、任意非可分三维周期材料/几何，单次完整流程≤172800s、约2TB整机保留系统余量且ownswap/OOC=0。有限直接authority不是目标规模生产架构；生产仍需分布式/matrix-free作用、streaming DtN、有界粗问题和可扩展Full3D迭代。

本次实际读取最新ref/目录/README/response/专题、关键门/费用、作用及审核代码、上次review之后8个提交的完整改动清单；同blob的既有task、根/目录规则和补充限制继续复用。目录未出现新supplement或Review V53。完整本地Review V52与已有远端blob一致。未SSH工作站、未取得全部ignored科学数组、未新跑PDE或现场测RSS；以下数值均为仓库recorded measured，不是本审阅新实测。

## 1. V54结果与收益裁决

依据：[Response V54](response_v54.md)、[专题](outcomes/p_order_dtn_separation_v54.md)、[门分类](outcomes/records/gate_verdict_v54.json)、[科学比较](outcomes/records/hp_accuracy_checks_v54.json)、[费用](outcomes/records/resource_costs_final_v54.json)、[拒绝记录](outcomes/records/admission_refusals_v54.json)。

| recorded measured；同Z2网格 | 实际结果 | 接受范围与限制 |
|---|---|---|
| R7：p7/828 | true 1.92427e-11；dat下界1222.513s；采样峰14.1040GiB | 完整返回和actor原式通过；最终独立审核未完成 |
| R6：p6/828 | true 1.18713e-11；dat下界5007.167s；采样峰7.47690GiB | 同上；不把冷准备与缓存启动混称 |
| C：p7/1188 | true 1.92314e-11；dat下界2607.212s；采样峰15.2692GiB | 同上；旧637.599s失败保留 |
| p6：532→828 | scattered E/H 2.22459e-7 / 3.18387e-7 | actor完整增量通过；等待独立消费 |
| p7：532→828 | scattered E/H 5.38623e-4 / 5.44118e-4；逐mode功率1.65479e-6 | 真实有限模式敏感，未通过 |
| p7：828→1188 | scattered E/H 7.81718e-5 / 8.33245e-5 | actor有限相邻增量通过，接近门；不是无限mode收敛 |
| 同828跨p | scattered E/H 0.03413294 / 0.03410379 | 主要分歧仍在；不能宣布p7一定更准确或一定有bug |
| 新FE VERIFY / saved checker | CPU/SMT准入拒绝，worker未启动 | PARTIAL_FINAL_AUDIT_RESOURCE_GATE；不是checker数值失败 |

跨p输入、26个raw类的独立方向积分、保存场新旧求值与有限嵌入见证支持本次实现一致性。D的结果尺度FAIL与操作尺度通过必须分列；少数见证不证明全算子稳定性或所有最高阶周期迹均正确。不重跑整套D，不重新开展全局谱分析。

**收益一：缩小误差来源。** 模式增量对p7有影响，但从532到828并没有消除3.4%左右的跨p差；p6的模式变化很小。不能再默认“多加模式会解决一切”，也不能把p6/532的h通过自动授给p7/828。

**收益二：真正消费了准确准备包。** R7/C各复用26类p7完整raw张量，读取约6.80s/10.29s；没有重复V53约8945.75s的这组raw核生成。边界、局部凝聚、全局因子仍新建。属于确定性重复工作消除，不是NN收益；缓存启动不等于单次从几何开始的冷加速。R6无匹配类时从正确原核构建并保存，不能将p6/Z4缓存错用于Z2。

**仍未取得：** 完整NOTCH准确性、目标尺寸解、同精度端到端性能、2TB/48h或NN20。现有三份解不是无用测试，但也没有闭合目标。Task42extra继续自己的5nm学习波动greedy，NN-V3保持独立；本支不做M5/teacher/训练/NN-PC，不迁移或运行邻支代码，不通知或修改其窗口。

## 2. Q0：先补齐已有结果的独立消费，不能重算三份解

启动新PDE前，按V54 run index、queue freeze及producer receipts绑定R6/R7/C、比较数组和D见证。V54窗口已closed；在V55窗口内建立独立的`prior_audit_inventory`，费用属于V55补审并带V54父hash。**不得重开V54 ledger，也不得提前写V55全队列frozen标记，把后续新solve自己锁死。** 复用既有`verify_cost`数学循环，只允许增加显式清单/输出位置参数或薄adapter，不复制完整runner。

完成原计划中缺失的：新进程原未凝聚Cκ＋q63完整DtN审核、内部恢复和实际basis属性、独立保存数组checker及逐模式功率重算。旧场只读，factor/numeric/solve计数必须为0；允许重建必要的独立作用，不重建单元LU/全局因子或重做完整p/h积分。已保存共同积分数组足以重判其范数、selected、功率与门；一个缺失文件只阻塞对应证据，不能伪造它或重新扫所有旧文件。

为避免刚增加p7后最高阶周期迹错误被低阶嵌入见证遗漏，若现有收据没有覆盖**实际R7/R6场的物理切向连续性**，在这次已建立的FE环境中补一项有限检查：遍历实际共享内部面与x/y周期配对面，用原native字段和已有方向/MPC解释，在每面8×8 Gauss点检查包络切向跳跃；周期面在相同参考位置比较u，或等价地对物理E只施加一次正确Bloch相位。保留每面分子、场操作尺度、最坏面和几何/方向身份，整体与非退化逐面操作尺度≤1e-10；近零面用冻结入射尺度，不以相消小量作唯一分母。不能要求法向E连续，不能要求离散H的切向迹强连续，也不能只检查slave存储为0。该检查只读保存场、无新JIT大矩阵/求解，目标≤300s；已有同对象等价证明则直接复用，不重复测试。

Q0完整目标≤1800s，受总窗约束。若仅checker/API/描述字段错，最小修复并消费原件；若证明物理映射/原式错，隔离其依赖，按§4修复槽重解受影响的同p/M父case，旧失败不改判。不要将新checker实现错误直接认作旧物理解错误。Q0完成即继续H7，不在补审PASS或提交代码后等待下一份review。

## 3. 固定物理，新计算只改变空间分辨

沿V51–V54全精度descriptor：s=7/135；x=s×(0,16.5,25,33.5,50)，y=s×(0,6.25,12.5,18.75,25)，z=s×(−10,0,40,80,120,130)。真实NOTCH仍按原几何盒和材料标记，不沿y复制、不改实体形状；λ0.7nm、grazing1°、azimuth5°、s偏振、幅值1。Si n=0.999885140474+4.32477054e-6i，ε=n²、μ=1，air=1；材料表hash `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。不索要或替换材料。

```math
E=e^{i\kappa\cdot x}u,\qquad C_\kappa u=\nabla\times u+i\kappa\times u,
\qquad H_{code}=e^{i\kappa\cdot x}C_\kappa u/(ik_0\mu_r).
```

κ保持物理入射值，包络双周期；完整trial/test交叉项、原入射RHS、所有内部特解及非零端口支撑、原未凝聚oracle保持。所有新主case固定828：m=−11..11、n=−4..4、上下×s/p。不改成二维/单向传播，不将物理场投回粗多项式空间，不增加或裁剪模式。

| 角色 | 原区间划分倍数 / p | cells | 独立FE / trace / 内部（derived） | 含828凝聚行 |
|---|---|---:|---|---:|
| H7，主计算 | (1,1,4) / 7 | 320 | 330848 / 88928 / 241920 | 89756 |
| T6，有界独立对照 | (2,1,2)或(1,2,2) / 6 | 320 | 209664 / 65664 / 144000 | 66492 |

现场核对MPC/原生维度，不能删行匹配公式。H7准确对应“同p7/828的Z2→Z4”，父场为V54 R7，不是旧532的B或p6的A。T6父场为V54 R6，在同p6/828上只细化一个横向；这不是再次升p，也不是V15局部NN表示。两条路径均从物理零初值独立求解，不读取旧解作为RHS或warm-start。

### 3.1 H7：先看高阶解对z分辨是否仍敏感

Q0及容量通过后直接完成H7。复用原MUMPS/精确端口坐标，至多两次既有残差精化，无ordering/shift/BLR/OOC/PC扫描。返回先原子保存完整u/port/κ/mesh/MPC/实际descriptor/source，再审核、释放全局factor和矩阵，最后后处理。

主比较R7→H7按全部原门。另计算R6与H7的同828场差，**只用于观察跨p分歧是否保留，不要求H7同时贴近两个已经相差3.41%的旧端点**。不得再次构造三角不等式上不可能满足的准入门。旧p6/532的h通过只保留为历史。

### 3.2 T6：避免只会沿z反复加密，但不强迫跑满

若跨p分歧未被可信实现修复消除，且剩余预算能覆盖完整T6、比较及独立审核，允许一次T6。H7场增量FAIL不是阻止T6的条件；H7容量阻塞而T6安全时也可运行。若时间不足则明确not_run，不降低精度强行塞入。

横向在新计算前冻结：从已补审R6保存包络，用已有`gradient_indicator`计算x/y的`sum h_K,d² integral(|∂d u_s|²+|∂d Henv_s|²)`，取大者，精确平手取x。此层状背景去载波后横向导数为零，可复用原helper；不拟合参考场，不凭E_y分量占比选y。这只是选择有界对照的指标，不是已认证误差估计。只算一次，q15及原尺度固定；不能看两个细化解后挑有利方向。

主比较R6→T6；与R7的差作单独诊断。不强制再作H7/T6全对照矩阵。没有资源时不运行T6，也不改成新的toy problem代替。最多两项计划新solve；若Q0确认原数学错误，最多另有一项受影响父case修复solve。公共错误需要修两份父case时取消T6，修复父场后H7为第三项。总计最多三份新完整solve；仅输出错误不占solve槽，也不得借故重解。

## 4. 判定与继续，不把有限一致性写成目标通过

| 观察 | 合理解释与本轮动作 |
|---|---|
| Q0独立审核不一致 | 先分清checker错误与科学错误；同轮最小修复、补审或受影响重解，不绕门 |
| R7→H7变化大 | p7仍有z分辨敏感；保留真实场，不说p7必然更准，不再加Z8/p8 |
| R7→H7很小，但R6/H7仍差很大 | 不是仅增加z就能关闭的分歧；用获准T6检查另一轴，不宣布收敛 |
| R6→T6明显变化且与p7场的差收缩 | 横向分辨参与的证据；不能把p7场指定为真解或将收缩当严格误差界 |
| 两项h增量均小而跨p分歧仍大 | 不再自动批准相同类型hp/mode循环；下一步应是一个有针对性的离散稳定性/更独立表示对照，非NN或无限加密 |
| 某组完整增量通过 | 只授该p/M与该网格对的有限h一致性；新网格未测mode变化，不自动继承Z2的828→1188门 |

所有新场都要求：原未凝聚true/native/增广/port各≤1e-6，内部直接目标≤1e-10；恢复/MPC/操作身份≤1e-10；total/scattered E/H/scaled-curl、固定240 selected及参考面复通道增量≤1e-4；R/T/A/A_volume增量及独立能量≤1e-5、逐mode功率≤1e-6。共同物理细分、q23/q31操作≤1e-10、旧near-zero规则不变。selected在人工细面按既有高侧规则；不得只用总场或总功率通过掩盖散射场FAIL。

所有模式按物理键/参考面匹配，raw辅助系数与物理参考面复振幅分列；不拟合幅相、不换分母、不归一化守恒。场比较中的同背景相消保留完整复交叉项，不能先投影一方再当独立误差。最大p、最新结果或最小代数残差均不自动成为连续真解。

## 5. 容量授权先落到代码，再开始昂贵准备

**仅V55上述有限authority允许规划同时≤64GiB、warning80GiB、采样整树停止96GiB、装配/symbolic行数≤100000。** 这是新增的研究配额，不是实测容量，也不是每进程96GiB；旧32/40/48及80000门不改判。H7的89756行不能继续被旧授权界直接拒绝。不得改全局默认或邻任务预算。

V54 p7/Z2/828的numeric规划23.6469GiB仅作较大case的起始信息；不能线性外推当H7准入，更不能因为旧峰14.10GiB而直接factor。实际mesh/MPC图、未舍入raw/方向类、局部LU/recovery、全部边界支撑、CSR和缩放副本、缓存与后处理重叠先规划。全部路径保持：

```math
RSS_{tree,live}+2\max(INFOG16,INFOG17)\,10^6+2\,2^{30}\leq64\,2^{30}\quad\text{bytes}.
```

INFOG缺失/溢出/不可靠或装配/新symbolic超过上限则不做numeric；固定ICNTL22=0与现场两倍decimal-MB额度，保留旧MUMPS选择。参数从真实resolved明确传到launcher、watchdog、assembly、CoordinateFactor/AnalyzedDirectFactor、numeric_plan与collector。只作旧标量16/32/64和越界的轻量回归，不造大矩阵来测预算接线。

继续MPI1、数学/CPU1、Loader0、GPU0、ownswap/OOC0；一个actor、一个全局因子。每stage现场选合格物理核心、避忙SMT；MemAvailable≥max(128GiB,有效物理内存10%)+384GiB邻增长+96GiB自身停止预算，既有规则更严取更严，effective cgroup余量及原PSI门保持。全48核被拒绝不是允许覆盖邻任务亲和性的理由。明确错误的自身核盘点可最小修复并保留反例；真实资源不足不叫bug。

本批至多两个前台资源观察episode，每个≤600s、累计≤1200s并计入总窗；不承诺后台自动重试，不以换case/把FE叫checker绕过准入。释放自身负载、原门恢复后才重入；持续不安全就保存可达结果，不关闭监督、不改邻任务或系统ABI/BLAS/CUDA/swap/governor/锁。

## 6. 复用准备、让普通bug在同一工作包内闭合

优先核对V53/V54准确raw provider及准备包；相同p不等于相同J，Z2→Z4或横向细化不匹配的类允许一次原正确核生成并保存，不近似合类、不改坐标追命中。p7/Z2缓存不得直接冒充H7全部类；新网格/模式下C/D/H、局部凝聚及全局因子仍按实际身份构造。before expensive prepare先计实际hit/miss类、用既有每类时长规划：若预计主解加审核已耗尽预算，先取消T6，不为凑结果删审核。

继续现有场求值乘法结合优化，缓存额外workspace≤2GiB计入64GiB总规划；exact hit为0时只保留当前块，不宣称命中加速。不新写六Gram/sum-factorization/NN生成器或通用缓存框架。准备包读写、独立审核、失败/冷却全部计费；fresh N=1、缓存增量、历史必要费用分列，unknown不填0。

每份解返回立即写最小合法科学状态，audit/checker/文档失败优先只补消费；每份独立审核也先逐状态原子保存，再写总表，不能最后一个stage失败丢掉前面已审结果。新场审核安排在其返回后的下一个可用阶段，不把全部审核拖到所有新case之后；已审同source/身份不重复。

普通API/shape/dtype/路径/role/schema/序列化/临时文件rename错误：定位→最小修复→受影响targeted回归→继续。没有bug个数式停工门；同根因两次失败须更换诊断或复用旧正确路径，不能第三次盲重放。累计意外修复与重放≤2h且受全局窗口限制。数学/ABI/数据身份/监督不可信先隔离，数值不一致不是任意改材料/模式/精度的理由。

不例行全库pytest、CI、全仓索引、全部历史artifact重哈希或旧FLAT/旧p阶/旧模式campaign；不重跑已经完成的D或cache微基准。只做父审核清单、真实切向检查（如缺）、p7/三轴/行数与资源贯通、条件T6及保存链的targeted检查，相关Ruff/compile和一次紧凑文档检查，元数据目标≤20min。只读一个所消费父文件时核实其hash，不扫描邻任务大日志。

## 7. 一次有截止的执行包与证据交付

从首次工作实时UTC/monotonic/boot_id冻结7h总窗；科学有载≤5h、最后45min收尾；新比较及独立验收至少预留3000s。Q0目标≤1800s、T6选择与轻量新接线不能挤掉主解；所有实现/等待/修复/准备/审核/IO计入，不刷新旧V54窗口。每次上下文恢复、新stage、commit/push前读实际钟，不依摘要剩余时间。

主序列：Q0逐状态补审＋实际切向检查→容量与case预检→H7完整解及其独立审核/主比较→预算内T6及其审核/比较→轻量增量结算。若H7容量受阻而T6安全，直接推进T6。若共同物理或监督不可信，暂停依赖计算并完成可独立工作；不能仅因Q0完成、代码提交或一个普通FAIL就等待下一份review。

最多3份新完整solve（含已确认科学错误的受影响父case），最终场集合最多6个去重状态；不得为凑表重算R6/R7/C或再加模式、Z8、p8。新ignored≤16GiB、Task042去重累计≤84GiB、free≥50GiB、交付预留512MiB。新field/raw包按需求保存，旧失败不删，不复制父大包；只在阶段边界盘点存储。计费给真实exclusive/未知区间，不叠加inclusive父子计时，sampled RSS不称连续硬峰，shared-workstation性能不声明无争用速度比。

复用`phase_notch_hp`、现有raw reader、原弱式/边界与场比较、`verify_cost`和保存checker；只加薄V55配置/队列与显式父审计接口。新数值小核进入src，不为每个case复制数百行runner。

实现、targeted回归、commit clean及validate后，按Gate运行待创建入口：

```text
input/task042_neural_coarse_inverse/v55_prior_audit_completion.dat
input/task042_neural_coarse_inverse/v55_resolution_preflight.dat
input/task042_neural_coarse_inverse/v55_notch_z4_p7_m828.dat
input/task042_neural_coarse_inverse/v55_notch_transverse_p6_m828.dat
input/task042_neural_coarse_inverse/v55_verify_cost.dat
```

正式命令统一`python scripts/run_case.py <one-run.dat>`；入口不存在时不能声称可运行，T6未准入不盲跑。父补审dat不得暗藏完整solve；必要修复参考另建明确dat并记入solve总额。保留input_original.dat、resolved_config.json、run_manifest.json、input/physical/discretization/material/mode/source/array hash及run_summary、环境与全过程资源。旧场身份、新审核producer、新solve源码和文档HEAD分开。

交付`response_v55.md`、`outcomes/spatial_resolution_audit_v55.md`及紧凑records：父审核补齐/仍缺项、两条h结果及跨p诊断、全部E/H/curl/240点/828模式/功率、真实容量与费用、raw hit/miss、修复/补审/资源拒绝、唯一下一工作。分别报告actor判定与独立checker判定，不由status反推通过。README/summary/两总账仅追加短入口，旧task/review/response/raw保留；GitHub实际视觉取不到如实NOT_VERIFIED，不为页面重跑PDE。

只在canonical工作树安全fetch/ff-only本分支；不reset/stash/clean、不改其他worktree，不强推或merge。只推送`git push origin HEAD:refs/heads/task42_neural_coarse_inverse`；核对remote完整HEAD、clean/upstream、closed/active null、后代清场和锁释放后向用户交付暂停。不自动通知隔壁或新开下一窗口。
