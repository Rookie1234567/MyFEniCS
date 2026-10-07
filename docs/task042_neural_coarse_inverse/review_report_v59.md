# Review V59：保留局部装配收益，在同一微网格上释放宏面切向自由度

## 0. 裁决、最终目标和本轮交付

**V60按有限范围接受，`pass_with_qualifications`。C67同空间再现和存储改善成立；H2原式、完整恢复及输出成立，但场准确性没有闭合。不得把局部一个单元的r2/r4通过升级为全域准确，也不再原样增加内部p或内部细分。**

下一批为 **V61_FACE_TRACE_ENRICHMENT**：复用V60已保存的微网格、内部因子和局部装配，在相同微p6空间中增加一组明确的宏面切向函数，求完整三维解。首先释放x法向宏面上的内部切向自由度；随后在同一空间上加入y法向宏面的同类自由度。宏边、z法向宏面、内部微网格、物理材料与828模式保持不变。有限的保存场面残差检查服务于这个真实计算，不作为一轮独立诊断的全部交付。

这项工作针对的blocker是：**H2已增加大量宏内部自由度，却仍把宏接口限制为p6；尚不知道这个接口限制给全场带来多少影响，也没有取得精度与接口规模之间的实测关系。** 原始p7缺陷建议有价值，但单独再测一次不同空间的缺陷仍不能给出改进后的场。本轮把检查和实际接口扩充放在同一包中，不预设接口限制是唯一原因或新场必然更准。

```text
repository          = Rookie1234567/MyFEniCS
execution_branch    = task42_neural_coarse_inverse
canonical_worktree  = /home/fenics/Projects/NN-Lab
review_date         = 2026-10-08 (Asia/Singapore)
reviewed_HEAD       = b733f988607c344cd7cebe164355e5e89dea0bc4
latest_commit_UTC   = 2026-10-07T21:50:36Z
latest_commit       = docs(task042): close V60 costs and verify final delivery bytes
latest_response     = response_v60.md
previous_review     = review_report_v58.md
previous_review_SHA = 7514fbedf6253807966f0aad7b1b864e908efd8e
original_base       = ccd357885f7f9be84efe3be07868cc94f13d93fc
next_batch          = V61_FACE_TRACE_ENRICHMENT
required_response   = response_v61.md
new_global_solves   = two_planned; at_most_three_including_scientific_repair_replays
NN_training_PC      = NOT_AUTHORIZED_THIS_BATCH
merge               = NOT_APPROVED
```

最终目标不变：原50×25nm周期、z=−10..130nm，真空0.7nm，周期单胞内任意非可分三维材料/几何，complex128 Nédélec H(curl)，x/y Floquet、z完整Fourier-DtN；单场必要准备、求解、恢复、输出和审核≤172800s，十进制约2e12B是整机内存，必须留系统余量。本轮仍是缩尺Full3D有限authority，不是Hybrid，不授原尺寸或可扩展生产资格。

本报告明确覆盖V58“最终接口一律33660行”和“不得提高接口分辨”的限制，只授权下述两组相容宏面增量；不改变微p6、r2、原场门或物理方程。不恢复旧窗口，不重新开启内部p9/r4全域、uniform hp/M/gauge扫描、新NN或新PC。

## 1. 实际审阅及已证实结果

审阅了固定HEAD的response/summary、上一份完整review、规则/仓库原则、原task同blob身份、12次后续提交差异，以及局部布局、两级响应、宏映射/装配/恢复和保存接口源码。任务目录没有检出新增独立supplement文件；历史规则和task按未变blob继承。没有SSH、没有读取工作站完整ignored场数组、没有审阅端新PDE。下表measured均为仓库记录；本报告的新方案均为planned/not_run。

证据入口：[V60回应](response_v60.md)、[完整专题](outcomes/local_assembly_subcell_response_v60.md)、[科学记录](outcomes/records/scientific_checks_v60.json)、[同空间再现](outcomes/records/same_space_reproduction_v60.json)、[局部响应](outcomes/records/local_response_v60.json)、[最终费用](outcomes/records/resource_costs_final_v60.json)、[目标缺口](outcomes/records/target_gap_v60.json)。

| recorded measured | 结果 | 裁决 |
|---|---|---|
| C67/M67同空间再现 | scattered E/H约1.38707e−12，240点及全部物理复通道通过 | 局部装配没有可辨识地改变该离散解 |
| 最终存储项 | 141754824 → 28510524 | 约79.89%减少是记录比值的derived结果；不是目标图估计 |
| sampled树峰 | 26.997310638 → 8.855014801 GiB | 约67.20%减少；有限同空间实现收益，不是连续硬峰 |
| C67完整T_N1 | 1287.2062114s；旧M67为1693.2687995s | 如实列两次观测，缺配平冷控制，不授精确速度比 |
| H2 mixed原式 | true3.08496334e−11、增广3.08217070e−11、port2.55116e−15 | formal/direct和内部恢复通过 |
| H2/R6 | scattered E/H6.42230e−4/6.20595e−4，240点5.58383e−4 | 超1e−4；不能用total/功率通过覆盖 |
| H2/M68 | scattered E/H3.84616e−4/4.10690e−4，240点3.38034e−4 | 仍FAIL，M68不是独立真值 |
| 局部cell74的r2/r4 | E/H2.17681e−7/4.27440e−7；固定432坐标反力差6.25721e−8 | 一个已选单元响应增量通过；其余p配对partial，不能外推所有单元 |
| H2完整部署与资源 | 观察恢复链5843.071058s；必要进程段3502.03991233s；峰13.292636871GiB | 无故障fresh数值冷T_N1仍unknown；不将进程段之和当完整冷成本 |
| 可消费作用 | 保存body-only局部Schur作用与装配体矩阵差约7.6e−16；唯一载荷483721840B | 可复用接口，不等于完整DtN、迭代或目标matrix-free资格 |

C67科学source为`e06d38742c64db261e6d6c30b91d6271965fb1f5`；H2 producer为`d42ac36b99bd758478da7ce42b34215826832676`；保存consumer/VERIFY为`f9b6d3886b59a3b1f549af62aec677347f2f8482`。旧存储停止与失败factor保留，合法H2保存后只补消费，没有重解。V60队列现已完成，不称“仍卡在bug”。

### 1.1 收益和限制必须分开

H2在每个宏单元保留4356个内部自由度，但外接口仍只有原p6迹。它的微网格ambient缺陷/RHS约0.00839936，是没有全部纳入测试的方向的缺陷，不是mixed求解失败，也不是已认证物理误差。此前约3.4%的跨p分歧不能用当前两个较小的同族增量宣告消失；没有H2/R7新配对时不编造其精确数值。

本轮不应重做C67、H2、旧FLAT、15表、q资格、24弱函数、局部r4或旧p/M/gauge实验。C67优化可以继续用；准确性研究转到接口，而不是重建同一局部装配。

### 1.2 与邻支的最新分工

已读取`task42extra_feinn_5nm@e67ceeef13308d195596c83c8601c5dc692943e6`的V31回应：真实块波动训练已完成，神经native残差0.378396、散射E误差约0.999052，M5和NN净收益未过；不能据此宣布所有NN无效。本Task42不复制其训练、M5、teacher或块读出研究。NN-V3仅核对ref`1f01ae46bbe21f17200350a46513ef5f33e5cf6a`，不推断本机状态。

工程线`0ddc939b093895bdf426bfd2d98852edc89d3f6a`最新V16合同保持已验证p6参考PC，研究Gx560构建成本并条件推进E1；本支不重写其PC/CSR/目标端口任务。dot ref为`15713d3e09b63f65511c7b7f61fa043fdb23dca5`，只核对ref，不冒称完整重审。没有修改、通知或启动任何邻工作树。

## 2. 新实验的物理与空间定义

保持V60 H2的实际宏/微几何、材料、κ及所有载荷。宏网格Z2为4×4×10=160hex，微网格为每宏2×2×2的p6，共1280hex。原κ=(8.94046081729244,0.7821889682108057,0)；s=7/135，λ0.7nm，掠入射1°/方位5°/s/幅值1；Si n=0.999885140474+4.32477054e−6i，epsilon=n*n，mu=1。材料表hash `55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2`。828模式、物理参考面/归一化、背景和完整Cκ不变。

一个宏面的2×2微p6切向空间，在宏面四周边线施加零切向条件后有264个自由度；原单宏面p6内部有60个。保留全部旧60维，再增加其204维独立补空间。这里的“零边线切向”不是把整个E矢量置零，法向分量不受这一条件约束。

新函数只在选定宏面有切向迹，在该宏单元其他宏面切向迹为零。与邻单元共享同一面函数；周期配对面只计一个独立实体。宏边上的原p6迹保持不变。**这不是统一p7，不是p7多项式插值到微p6后假称精确；新空间完全属于原H2的微p6 ambient空间。**

| planned角色 | 释放的宏面内部切向空间 | 独立trace | 内部 | mixed独立FE | 含828端口行 |
|---|---|---:|---:|---:|---:|
| 已有H2 | 无 | 32832 | 696960 | 729792 | 33660 |
| FX | 所有x法向宏面，周期识别后160面，每面增加204维 | 65472 | 696960 | 762432 | 66300 |
| FXY | FX再加所有y法向宏面，合计320独立面 | 98112 | 696960 | 795072 | 98940 |

这些是derived，现场用真实实体/MPC核对。局部宏边界坐标由432增加到FX的840、FXY的1248；每宏756个二级内部微接口和8×450子内部都不改变。z法向面、宏边和微p6内部本轮不扩充；未约束ambient独立FE仍834048，不能将其全部暴露给全球求解。

x方向先行是固定设计：既往同p的x分辨敏感，而y/z若干配对较小；这不是证明x宏面是唯一根因，也不根据本轮结果偷偷换轴。FXY是预授权的嵌套交叉检查，不根据某个模式或参考场挑面、挑秩、调参数。

## 3. P：同一微空间中的面补空间和保存场缺陷

### 3.1 几何决定的面基，不学习解

用原Basix实体矩、`MacroLayout`/`child_interpolation`及方向信息，在一个canonical宏面上组装264维的微面内部切向空间。原p6面内部插值记为P_f（264×60）。构造正的物理切向L2面mass矩阵G_f；经Cholesky和固定QR取得补空间Z_f（264×204）：

```math
P_f^H G_f Z_f=0,\qquad Z_f^H G_f Z_f=I,
\qquad \operatorname{rank}[P_f,Z_f]=264.
```

仅按数学实体结构选择零迹行；不得幅值drop、伪逆截秩或以参考误差训练Z_f。原60列完全保留。相同几何/方向可共享只读块，参考面顺序/基符号/规范与hash冻结；不能为每个cell重存全套稠密面基。

必须正确处理3D切向分量、covariant Piola、微面内共享边、宏面旋转/反射和x/y周期复对偶。一次真实两宏单元共享面及周期面对照覆盖：零宏边切向、其余宏面零切向、旧空间包含、唯一owner/复对偶。操作门1e−10、复dot门1e−12。只补新增数学，不重跑全部旧Nédélec/MPC资格。

### 3.2 用已存H2原式向量看新增方向，不再重新积分全部body

H2已有PUBLIC_BASIX微空间独立残差，优先读取其原数组和身份。用新面基的全局注入I_f计算`d_f=I_f^H r_H2`，共享和周期贡献先正确组装，再求每面范数；不能把每侧局部残差平方相加当共同面残差。

若基不是物理mass正交规范，用同一正Gram的对偶尺度`d_f^H G_f^{-1} d_f`；给出原复向量、绝对量、面积及固定物理尺度，不只报告一个任意归一化小数。只在本批同一微空间内比较，明确它不是全H(curl)对偶范数或误差上界。内部测试已满足时，不同合格内部延拓应给出一致面反馈；用至多两个面核对该事实。

优先所有x/y面；z/宏边仅汇总现有ambient量，不另开完整p7映射或谱诊断。P总目标90分钟，其中保存缺陷消费目标20分钟。诊断接口超时可保存partial，已经合格的几何映射/原作用仍可推进FX；实际映射或原式不可信必须先修。不能以诊断未显示大收益作为禁止真实FX/FXY求解的循环前提。

## 4. 复用局部响应，而不是重建高阶或全局微矩阵

新接口注入后，每宏边界为B_e t_e，其中B_e保留H2旧lift并追加相应面列。仍先消去子内部，再消去756个宏内部微接口：

```math
\begin{aligned}
D_e &= S_{bb}-S_{bm}S_{mm}^{-1}S_{mb}, & h_e &= f_b-S_{bm}S_{mm}^{-1}f_m,\\
K_e &= B_e^H D_eB_e, & g_e &= B_e^Hh_e.
\end{aligned}
```

由原局部装配器形成ΣE_e^H K_e E_e及828端口。禁止global micro/high Schur和global Q^H S Q。**增加的是哪些宏面方向可以全局协商，不是改变内部方程、材料、载波或开放边界。**

源码`MacroResponse`已保留二级LU、Sib/Sbi及子Schur，适合重用。H2旧432×432宏Schur本身不足以推断新增列的交叉块；必须从真实子Schur重组局部Sbb，配合相同756内部因子计算新增响应。旧wrapper校验lift完全相同，不能伪造旧manifest绕过；新增明确的只读内部求解服务，再生成带新lift身份的响应包。

只对缺失的类/块重新构造；每列批次≤16，最多单宏1728×1248临时lift/作用块。不要同时驻留160套完整D_e/扩充lift；基按canonical面共享，响应按精确类共享或有界加载。内部因子依赖物理/微几何/κ，而新响应还依赖面基/方向/选择，缓存键必须分层，不能因body相同误复用旧low_schur。

x/y面内部补函数在z端口面具有零切向迹，端口空间理论不变。复用V60匹配的完整微空间q47/q63包，先用新增列验证其z迹/C/D作用为结构零，再做原复对偶拉回。原828模式和非零入射/内部载荷全部保留；不能删除真实非零边界项来满足预期。若原式证明零，则新增端口行/列无需重新Fourier积分，包读取费用照计。

同一operator与RHS装配身份在各route冻结，FXY不能直接使用FX解作为物理初值；两个case均从零求完整问题。允许复用已资格的数值准备对象，但如实计作prepared-start，不称fresh冷启动。每个case保存全部必要部署边界时间、首次准备依赖和未知费用，复用数据不代表免费。

## 5. FX→FXY：两项完整计算和必要资格

用同一个小型复数非Hermitian块问题，检查旧/新面空间包含、非零内部与端口载荷、直接受限解/两级凝聚/恢复以及共轭对偶。至少一个实际宏单元核对新局部形成和独立微body作用；关闭附加列时用已存H2的旧局部Schur或真实作用见证再现，不重解H2。

新p6宏面方向共享后，实际global graph按E_e支撑重算；旧34360848图门不能套到新空间，也不能任意把`admitted`设真。FX/FXY的局部支撑最大840/1248，稀疏装配计入所有实际列和端口块，不能幅值剪裁。先容量再numeric。

顺序：P与短数学资格 → FX完整solve/恢复/保存/独立审核 → FXY同项 → 一次增量场比较和费用收口。FX准确性比较FAIL不取消数学/资源可信的FXY；FX也不必先取得速度优势。FXY若真实容量不满足，保留FX完整结果和明确symbolic/对象证据，不改成未授权配置或赌OOM。

必须实做两组主比较：H2/FX、FX/FXY。FXY/H2可在同一积分批次顺带计算，R7/FXY仅作为一组预算允许的跨表示诊断，不能要求新场同时靠近已不一致的所有旧场。比较在相同微几何上分别重建物理gVh场，E/H/curl、240点、828复通道/功率/体吸收齐全。不投回宏p6，不拟合相位，不四舍五入过门。

只增加面测试空间不保证不定Maxwell场误差单调下降。H2→FX变化较大可能说明原限制重要，但不是新解必然更准；FX→FXY很小只说明该增量小。均不得授全空间、连续、所有模式或原尺寸准确性。

### 5.1 正式残差与ambient缺陷

沿微p6独立body q15及完整q63边界，得到全部ambient向量，再以新J_F^H拉回：

```math
r_F=J_F^H(b_\mu-A_\mu J_Fx_F),\qquad
r_{\mathrm{ambient}}=b_\mu-A_\mu J_Fx_F.
```

所有宏内部、所选宏面新方向、原p6迹和828端口均进入正式门；未释放的z面/宏边缺陷继续单列。相同微ambient使H2/FX/FXY的缺陷更可比，但仍须注明系数尺度，不称物理误差。

formal true/native/augmented/port各≤1e−6，direct目标≤1e−10单列；恢复/MPC/identity≤1e−10。最多两次既有精化，不对ambient缺陷无限精化。原场增量门：total/scattered E/H/scaled-curl、240点、参考面复通道≤1e−4；R/T/A/A_volume与独立能量≤1e−5；逐mode功率≤1e−6。共同积分q23/q31、操作差≤1e−10，必要一次q39。几何/数学变化前后验证绑定实际source。

## 6. 时间、资源和不被普通bug卡住的执行要求

新总研发窗口10h、科学有载≤8h，最后1h收尾，首次UTC/monotonic/boot冻结，所有实现/失败/修复/等待/准备/比较/IO都计费。不要重开V60窗口；上下文恢复后读取实际时钟。两项计划新global solve，最多第三项仅用于确认后的科学修复重放。每项numeric启动前，保留至少1800s供该case输出/独立审核和最终交付；预留不足取消附加诊断，不削减完整验收。

继续64GiB同时规划、80GiB警戒、96GiB采样整树停止、100000凝聚行。FX66300、FXY98940仅是行数许可，不是numeric通行证。仍执行live树RSS+2×可靠INFOG16/17(decimal MB)+2GiB≤64GiB；没有可信估计则不分解。保留原MUMPS排序/精化/ICNTL22=0、无BLR/OOC、MPI1/math1/GPU0/Loader0、自身swap0、CPU/SMT/PSI/cgroup/宿主与384GiB邻增长余量；一个自身heavy actor/一个global factor。不改邻任务或系统环境，不依赖OOM探容量。

本批局部常驻缓存可计划≤16GiB（包含在64GiB内，不另加），显式覆盖V60的8GiB局部缓存上限；临时面表/作用workspace≤2GiB，优先分块/LRU而非扩大常驻。新增ignored≤32GiB、Task去重累计≤180GiB、free≥50GiB。先核算两套解/原式向量和原子写入双份所需空间，保留≥512MiB安全余量。新包使用只读父引用或同字节去重，不复制整个V60 bank，也不删除旧失败。不能等解已返回才首次检查保存容量。

普通API、shape、dtype、序列化、路径、预算传参或collector错误，同轮定位—最小修复—受影响回归—继续；不按bug数量结束。累计修复/重放≤2.5h并受总窗限制，同根因两次无效要换诊断，不第三次盲重试。已返回解优先消费，writer失败不重新factor。新面诊断桥的问题只隔离该桥；原作用/映射/ABI或监督真不可信则暂停依赖计算。旧面基不能构造新增空间，不能回退旧H2冒称完成FX。

P的数学核心目标90分钟，可用原正确的逐面/逐宏实现先完成，不为性能微优化拖住全域结果。新局部加载器缺项可用原正确child核补对应块；恢复了哪些、重建了哪些逐项计费。不重跑C67、旧FLAT、旧Q0/gauge/M、24弱函数、局部r4或全部15表资格，不例行full pytest/CI、全仓索引和全历史hash。只做新增面空间、装配、恢复/保存接线的targeted回归、相关Ruff/compile/dat validate及一次简明文档检查。

## 7. 2TB/48h判断与下一步边界

本轮不能以增加接口换精度后，又隐瞒向量库变大。restart32的标准FGMRES主库仍按V33+Z32共65条，另有x/b/r和工作区；当前FX/FXY trace+port主库derived为68,952,000/102,897,600B，非实测分配。内部696960行不进入该接口库，完整微场按块恢复。

复用旧Nx80/Ny80/Nz400、268156模式的**未获精度资格**情景：H2接口65条约0.528TB，若对所有相应目标面照搬FX或FXY，则约1.071TB/1.614TB，尚无原算子、PC、其他向量、恢复、MPI复制和系统余量。这个算术反而说明，**本有限实验用于测出哪些接口信息重要，不能把所有面全量扩充不加选择地推广到2TB目标。** 全部微FE向量库约12.125TB、逐cell复制稠密Schur约7.644TB的旧警告继续有效，均非准确网格下界。

必须交付实际面增量对场/残差的作用、nnz、factor填充/峰、内部缓存/新增面响应/恢复、准备复用费用、trace作用与输出费用。不要再复制一张相同规模规划表。若面增量显著、完整场更稳定，下一pilot才讨论有界/局部选择的接口表示与分布式trace迭代；若新增面缺陷小且跨p仍大，收口本面族扩充，选择一个独立离散或稳定性authority，不自动FXYZ、升宏边p或加内部r。

未来生产架构仍为局部有界消元/作用、matrix-free分布式接口、可扩展波动纠错、有界粗问题、streaming DtN及分块恢复。有限direct在此只提供新空间authority；邻支PC的3步结果不能继承，NN不承担未解决的离散误差。本批没有NN训练或NN收益。

## 8. 提交、正式入口和交付

公共面空间/方向/宏响应适配进`src/solvers/`，复用现有`subcell_response_kernel`、`subcell_macro_deployment`、`local_trace_assembly`、保存bank、PUBLIC_BASIX和无JIT输出；只增加薄的case/scope入口，不复制大型runner。先定点回归、commit clean、validate，再按资格activation/监督运行这些待创建的one-run输入：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v61_face_trace_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v61_face_x_enrichment.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v61_face_xy_enrichment.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v61_compare_verify_cost.dat
```

preflight不暗藏global solve，最终consumer不暗藏factor。FX/FXY各自一个明确计算，case身份同时记录宏/微网格、微p、释放面族/204列基、宏边/z面限制、mixed/ambient与端口坐标，不能只用一个p字段。输入原文、resolved、run_manifest、input/physical/source/数组/环境/资源hash全绑定。

C1提交面基和映射/最小回归；C2提交局部响应复用及两case接线。活跃数值期间不改变受检HEAD。代码commit、小测试PASS、一次准确性FAIL不是停等review的理由。所有合法返回向量、primitive计数、原式向量、积分块先保存，再做派生JSON；相邻合法步骤可继续，最终统一收口。

交付`response_v61.md`、`outcomes/face_trace_enrichment_v61.md`；records紧凑保存parent/source、face inventory/basis/primal-dual、旧H2面缺陷、FX/FXY原式与ambient、完整E/H/240点/828模式/功率/吸收、比较矩阵、nnz/容量/实际费用/采样gap、复用/修复/未运行及唯一下一pilot。完整per-face/per-macro数组留ignored，Git只存增量与父hash，避免嵌套复制数万行旧manifest。

summary/README及两总账追加简明新入口，旧task/review/response/raw保持。只推送：

```bash
git push origin HEAD:refs/heads/task42_neural_coarse_inverse
```

核对精确remote SHA/upstream/clean、closed/active null、清场与锁释放后交付用户暂停。不merge、不改master/邻支、不通知隔壁、不自动开新窗口。GitHub视觉未取得就如实NOT_VERIFIED，不因网页或文档问题重跑PDE。

## 方法依据与审阅端验证边界

实体/closure、插值及DOF变换依据[Basix0.10官方文档](https://docs.fenicsproject.org/basix/v0.10.0/python/_autosummary/basix.interpolation.html)；局部消元与接口恢复的一般条件见[MFEM静态凝聚说明](https://docs.mfem.org/4.8/classmfem_1_1StaticCondensation.html)。它们不证明本项目新面空间能达到准确性或速度目标。本报告的固定面补空间与FX/FXY是待验证的项目内设计，不冒充已有文献的完整Maxwell收敛定理。

审阅端只做了复数mass正交补、嵌套受限空间与局部凝聚/恢复的小代数检查，以及上述面数/自由度/库存算术；没有新Basix/FEniCS/PDE或工作站实测。所有新收益必须由V61实际场与成本决定。
