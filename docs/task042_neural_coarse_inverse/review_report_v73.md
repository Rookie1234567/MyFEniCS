# Review V73：保全881个宏包，关闭重复准备链，完成同一harmonic候选的真实求解

## 0. 裁决、目标与身份

**接受V74的部分构建、失败与费用证据；不接受将本轮视为完整执行目标已经交付。V74没有进入KSP，不能判定harmonic预条件器不收敛，也不能授予低内存完整解资格。批准V75_DURABLE_HARMONIC_COMPLETION：不换粗空间、不换PC，复用881个健康宏包，补齐79个缺项和完整新粗矩阵，通过实际全域见证后，在同一窗口完成一次原定FGMRES及全场验收。**

本轮消除的直接blocker是：准备结果没有完整持久化，恢复路径先重复昂贵前缀，源码身份过粗又可能拒绝健康缓存；阶段预算进一步阻断了尚未执行的求解。它属于求解器工程、内存生命周期与任务执行治理，不是新的物理模型或第三种预条件器。

上版由ChatGPT设置的4小时H硬门与14小时总窗分割过严；这也是本次未进入求解的原因之一。Codex遵守旧门停止是正确行为，不能要求其私自越过合同。本报告明确取消新批次的4小时H硬门，采用一个总截止和必需求解/输出余量。V74旧时钟、停止、失败及花费保持原样，不重新打开旧窗口。

```text
repository               = Rookie1234567/MyFEniCS
execution_branch         = task42_neural_coarse_inverse
canonical_worktree       = /home/fenics/Projects/NN-Lab
original_base_SHA        = ccd357885f7f9be84efe3be07868cc94f13d93fc
reviewed_result_HEAD     = 11b3011f97587877adf58814e36b83d0e099c6e9
result_commit_time_UTC   = 2026-10-11T17:47:04Z
result_commit_time_local = 2026-10-12 01:47:04 +08:00
review_date              = 2026-10-12 Asia/Singapore
previous_review          = review_report_v72.md
previous_review_commit   = 6fcc95ea94b869d738c00c5f3e11c7025dd52f13
reviewed_response        = response_v74.md
campaign                 = V75_DURABLE_HARMONIC_COMPLETION
required_response        = response_v75.md
ordinary_default         = UNCHANGED
NN_training              = NOT_AUTHORIZED
merge                    = NOT_APPROVED
```

最终目标仍是原尺寸50×25nm周期、z=-10..130nm、真空0.7nm、任意非可分三维材料/几何、complex128 Nédélec H(curl)、双Floquet/Fourier-DtN、完整复E/H及物理输出。十进制2e12B为整机内存，必须留系统余量、ownswap/OOC=0，单场必要构建至完整验收≤172800s。当前s=7/135缩尺问题不是该目标资格。

## 1. 审阅范围与已确认事实

本次实际读取最新refs、commit与上版review后的8提交文件差异，根AGENTS、仓库原则、docs规则/索引/公式规范、原task、当前README/summary入口、response全文、关键费用/身份/分区/lift记录，以及harmonic粗构建、study、scope和原coarse Galerkin/PC源码。任务目录完整树中没有独立补充任务书、目录AGENTS或已有Review V73。原task早期13.5nm/NN限制已被历次正式review覆盖，不重启首轮任务。没有逐行重审全部历史response或README的全部历史段。

审阅端没有SSH、检查工作站此刻PID、下载大型原始数组或重跑PDE。下列measured指执行机提交的记录，不是ChatGPT新实测。审阅端只运行了小型合成complex128代数检查，验证非互伴局部延拓、不同列映射的批乘与分块累加；最大相对差约2.48e-16，不替代实际FE/端口资格或收敛测试。

主要依据：[R1 Response V74](response_v74.md)、[R2 lift资格](outcomes/records/harmonic_lift_qualification_v74.json)、[R3 宏分区](outcomes/records/macro_partition_v74.json)、[R4 最终费用](outcomes/records/resource_costs_final_v74.json)、[R5 source绑定](outcomes/records/source_bindings_v74.json)、[R6 宏构建源码](../../src/solvers/harmonic_trace_coarse.py)、[R7 study与身份](../../src/solvers/harmonic_trace_study.py)、[R8 时间合同](../../src/solvers/harmonic_trace_scope.py)、[R9 Galerkin与PC](../../src/solvers/bounded_trace_pc.py)、[R10 历史摘要](outcomes/summary.md)。源码判断固定于上述reviewed HEAD。

| 固定0.7nm NOTCH / measured记录 | V74实际值 | 正确含义 |
|---|---:|---|
| 细层完整FE / retained+port | 1,943,745 / 1,177,293 | 待求物理空间没有减少 |
| 宏区域完成 / 总数 | 881 / 960 | 完成91.77%的宏数量，不是完成91.77%的求解 |
| 新局部numeric / triangular calls | 881 / 86,840 | 准备成本真实存在，因子均已释放 |
| 缺失宏ID | 881至959，共79个 | 下一轮只补真实缺项 |
| 宏内部行 / 最大单宏行 | 765,675 / 2,090 | 不是已消去的767,280个单元内部系数 |
| 保存lift数组载荷 | 993,648,360B，约0.925407GiB | 不是RSS，也不包含所有对象 |
| producer局部残差 / 运算尺度 | 3.14928402084e-14 / 8.72055996087e-16 | A/AJQ未保存，独立checker没有重算该局部残差 |
| 最大单宏双倍symbolic | 36,000,000B | 未触及8GiB单宏门，不是整套PC容量 |
| 全域Galerkin / 完整复对偶 | NOT_RUN / NOT_RUN | 局部结果不能替代全局资格 |
| 新完整E_H / 38+1 PC numeric / KSP | 未完成 / 0 / 0 | 无新完整场、原true或official R/T/A |
| 采样树峰 / 最大采样gap | 9.275627GiB / 2.944926s | 不是连续硬峰，不是完整解内存 |

第一次基础Galerkin耗时4210.528095s，约70.18分钟，但没有原子检查点；第二次因此重复前缀。第一次881宏后的退出由活跃时间重复计入触发，修复后保留原时钟。第二次最终触及原H阶段门。费用结算时本批elapsed为16778.811509s，已知不重叠命令下界13231.113316s；总窗口仍剩33624.215391s，约9.34小时。不能把worker、wrapper、嵌套阶段计时重复相加，也不能把未分段时间全部归因于BLAS。[R1][R4]

第二次H的原始classification仍是SIGNAL_STOP_SENDER_UNKNOWN，response另述14400.013s监督TERM；两种记录不静默改写。仅在收口时核对已有监督回执能证明的范围，无需为发信者追查重跑数学。[R4][R5]

## 2. 需要一次解决的工程问题

| 优先项 | 源码/证据判断 | 本轮明确修复 |
|---|---|---|
| P0 重复基础项 | build_harmonic每次先调用coarse_galerkin，之后才读旧macro；基础项未持久化 | 先做可恢复基础项，再补缺失宏；已有基础块不重复 |
| P0 缓存身份过粗 | study把整个harmonic_trace_coarse.py的SHA写入数学身份；仅改保存逻辑也会拒读旧881宏 | 保留旧source，新增明确的数学兼容收据；不修改旧identity、不删hash Gate |
| P0 阶段时间与总窗割裂 | 修复后的case_remaining仍把首次工作以来全部elapsed压进4h H | V75单独窗口/入口，取消H硬门和原6h I阶段门；保留总截止、KSP和资源界限 |
| P1 重复逐cell开销 | coarse_galerkin已限制到真实局部列，但逐cell重复稀疏抽取、打包、乘法和插入 | 有界同形状/同核批乘；不能谎称旧代码对每cell都乘7068列 |
| P1 准入/计数不一致 | 宏numeric源码使用max(workspace,2GiB)，未显式落实合同12GiB future；manifest又可把复用numeric计成新numeric | 统一预算来源；明确reused/new/recomputed计数和阶段共驻对象 |

这里不认定局部数学错误，也不把批乘必然加速当事实。真正要避免的是：优化未完成就一直不求解，或一次writer错误导致从头重来。优先完成持久化和健康复用；优化只有一个有限机会，必要时使用正确的逐cell备用路径继续。

## 3. 冻结数学与允许修改

保留25576tet/p5/828、真实NOTCH、全部内部系数、canonical Si、grazing1°/azimuth5°/s及原κ；38个RAS块、halo、writeback、p2骨架与7068粗维数不变。不训练NN，不引入谱截断、shift、吸收、ILU扫描或新p/h/M；不重跑旧R128/B128，不补旧失败尾部。

```text
mesh_sha256     = c470274ab6c64cee0b8eef09dbcdadadfac4c6ca229d7fc2b6e608ded62f540c
material_sha256 = 55aa34e55c5e3cc35f6849eddbd3bcc72d3b694d32bc4885299ef373acd676a2
physical_sha256 = df26b8cf28e1115bdb2eb9ac9b79e698596133305310d26c1d664f94e2c5be44
partition_sha   = b7d975207fb4b94c559f1bc82f16eeca010768af3a80523436c161031f3f1a1a
Z0_sha          = 536758160a20d38c5fc87781a192fd853d6f387164774181c12595d0daa3880e
packet_sha      = 9bef5add6398999c70c21c7f26a86833fc1eb46f98598c8503aa3c41743728da
left_sha        = ed8b1c592bd1ec4e557111ae0c0884fd3399003c8463580df4db27265ed0c29d
right_sha       = ad141cedffb64c1571943e95f74c74829e4ac06485fdddac7b7e89f9f51eb000
V74_math_source = 4a6071bafc0448818f51615d3ef080981040d36ba49e2153df77991470a0d1d0
```

全部实际路径从R2/R3/R5绑定的健康manifest解析，不猜同名文件。允许修改通用构建/缓存/计费/消费者和对应scope、research入口；数值内核留在src/solvers。用参数化scope或薄适配接V75，不复制另一套大型runner，不改邻分支和ordinary默认。

粗函数仍由同一p2边界值控制，在宏内部用原Maxwell齐次方程确定形状。它改变PC的基函数，不改变正式PDE或细层自由度。记Q为宏骨架与port，R为骨架p2加port恒等映射，J为宏内部：

```math
L_j=-A_{J_jJ_j}^{-1}A_{J_jQ}R,\qquad
Z_H=\begin{bmatrix}R\\L\end{bmatrix},\qquad
E_H=R^H A_{QQ}R+\sum_j R^H A_{QJ_j}L_j.
```

上式来自A_JQ R+A_JJ L=0，适用于这里的非Hermitian原块；不把A_QJ换成A_JQ的共轭转置。实际非零J-port驱动和反向L^H的port分量全部保留，原符号/缩放/MPC只施加一次。不能形成全局fine K/S或大骨架Schur，不造全局N×7068列库，也不逐列调用7068次全域作用。

## 4. A：健康资产接入，不重跑准备历史

V74保持closed且只读。V75在独立ignored子目录保存新数据和清单，引用旧881个lift及correction，不复制父大包、不覆盖旧JSON。旧38块CSR、V74分区和Z0直接复用；无需重建原960宏几何和旧全网格资格。

新增一份紧凑reuse_compatibility_v75记录：旧数学/物理/packet/尺度/分区/列映射身份、旧producer source、当前consumer source、相关代码diff，以及允许复用的明确理由。区分数学依赖与保存、日志、预算实现；不能把整个文件hash变化直接当成全部数学失效，也不能伪造旧hash使Gate通过。

对旧包作一次文件/成员hash、shape、finite、rows/columns与唯一owner核验；后续同进程重复消费复用已验证对象，避免每PC重新hash。检查原correction与lift的配对身份。以首个、最后一个及最大J的已保存宏为固定见证（重复则合并）：只重建其局部A/AJQ/AQJ，不factor，验证A*L+AJQ及保存correction=AQJ*L，均按1e-10原门。这是兼容性见证，不是假称重新审核了全部881个局部残差。

仅有保存/分组/计费变化、局部方程依赖未变且见证通过时，881个旧宏可沿旧source接入。若局部方程、材料、方向、尺度或映射真正改变，必须标出受影响集合；不能以“要推进”为由接受不兼容包。个别损坏只重建该项并另计费用；发现系统性不兼容则保存明确数学blocker，不静默重算全部960个。

## 5. B：基础Galerkin持久化与有界等价加速

基础项是尚未加入宏内部消元修正的粗矩阵。它只有7068行，但需要累加全部细单元贡献。对每个cell保留原局部映射：

```math
d_c=E_c(Z_B)_{I_c,\mathcal C_c},\qquad
G_{\mathrm{FE}}=\sum_c J_{\mathcal C_c}^{H}\,d_c^H S_c d_c\,J_{\mathcal C_c}.
```

这里C_c是该cell真实非零粗列集合，J_C仅作局部到全局列的选择。相同尺寸可批处理，相同Schur key可复用核，但各cell的d_c、方向、材料贡献及全局列映射不能混同。不能使用数值drop、近似合并或平移不变假设。NumPy matmul支持最后两维矩阵的批乘，但不自动加复共轭；实际实现显式使用conj和最后两轴转置。[R11]

**先使正确逐cell路径具备持久化，再尝试批乘。** 基础FE按确定的cell-ID块（默认每块至多256 cells，可因2GiB临时门拆小）形成有界粗贡献，记录覆盖集合/次序/输入身份/hash；每块完成即原子保存。预期覆盖25576个cell恰好一次，包括没有非零骨架支撑的cell也明确登记为零贡献，不用“无文件”暗示已经处理。

端口基础C/D/H单独生成并保存，完整基础矩阵只加入一次。完整base CSR、每个宏correction、最终E_H均有明确的组成清单。恢复从空累加器读取已提交的互斥块一次，或读取完整base一次后只加宏correction；禁止二者混用导致双计。使用临时文件、校验、同文件系统原子rename和最后提交的receipt；半写文件不能成为已完成对象。写失败只重做最后一个未提交块。

PETSc采用一致ADD_VALUES语义，取CSR或作数值运算前完成MatAssemblyBegin/End；不能在没有assembly的情况下混用INSERT与ADD。[R12] 不同时常驻所有块或全部宏F因子。旧V74没有保存的基础项确实需要新算一次，不能包装为免费恢复；新基础项从此可直接回读，不再因writer失败重复70分钟级前缀。

一次至多64个代表cell的原逐cell/批乘配对即可，覆盖已有实际方向、周期、材料和支撑形状；不新增PDE。记录抽取、打包、乘法、插入、IO的非重叠时间；真实相对/运算尺度门1e-10。批乘试验与局部调优合计最多45分钟，目标是减少开销，不是新增资格 campaign。达到上限或无明确收益就采用已检查的逐cell持久化路径继续完整构建，不能因此把整轮停在性能面板。

## 6. C：补79宏、完成E_H，然后直接求解

按V74同一宏块公式补ID881..959，旧健康881不重新numeric。逐宏J≤20000、双倍symbolic≤8GiB，lift+映射总≤8GiB、临时块≤2GiB；numeric之后保存lift/correction并释放因子。新清单明确列reused_count、new_numeric_count、recomputed_count和legacy_numeric_count，不能把读入881条历史numeric_count算作本次新分解。

完整E_H由基础项加全部960宏correction形成；必须新做E_H symbolic，不能使用旧E0替代。38块旧symbolic可用于事前规划，实际因子建立仍回读信息。数学Gate及80GiB PC总门同时通过后，接同一个common.iterate，不再停等一次review。

全域资格沿原两个固定复粗向量/seed7403，每个向量一次真实fine action：比较E_H*w和Z_H^H*Ahat*Z_H*w、检查全部宏J齐次行，门1e-10；另用独立复fine向量核验完整primal/dual配对，不能只用r=A*Z*w自检。保留绝对值、原分母和运算尺度。不能只看局部producer PASS。少量明确接线错误同窗修复并重跑受影响见证，不开FLAT、hp/M或旧控制PDE。

预条件仍为coarse-first，非B128两侧反馈：

```math
C_H=Z_HE_H^{-1}Z_H^H,\qquad
z_c=C_Hr,\qquad z=z_c+B_{\mathrm{RAS}}(r-\widehat A z_c).
```

保持RIGHT FGMRES/restart128/max256、原norm/正交化、retained零初值和原内部特解。不得用V70参考场、V73失败场或人为准确方向warm-start。细层action/RHS/port均不变。新PC不要求单次收缩才准许FGMRES；一次coarse-only分账并入必要资格，不调参追求漂亮诊断。

一个计划KSP.solve，最多256累计有效步/10800s累计KSP；全批真实全域列作用≤800，其中资格≤12。所有层显式使用同一budget，轻量逻辑验证跨旧600限制，不用实际PDE测试数百次计数。只有已定位实现错误且没有合法终态时允许一次同候选retained续算；source、总步数、作用、已花时间不清零。不因数学停滞换参数重开。

## 7. 全场与科学Gate不得缩水

每32步、候选通过及末态核验原式；合法候选先保存retained/RHS/尺度/packet/source。先释放KSP及38局部+1粗因子，记录RSS下降，再恢复全部767280个单元内部系数和完整物理。writer、JSON、图表或checker失败只补消费，不能为文档重新factor。

| Gate | 固定标准 |
|---|---|
| retained显式true | ≤1e-11 |
| 独立true/native/augmented/port | 各≤1e-6；不能拿其中一项替代另一项 |
| 恢复/MPC/Schur-original | 各≤1e-10；direct目标1e-10另列 |
| 同离散total/scattered E、H、curl，全域/原240点/复通道 | 原严格1e-6；候选与V70两个固定分母均报告 |
| R/T/A/A_volume差与逐mode功率差 | 分别≤1e-8与≤1e-9 |
| 独立能量闭合 | ≤1e-5；不能用A=1-R-T代替体吸收 |

全部828物理复通道和逐mode功率、六场及原240点必须完整输出。候选冻结后唯一VERIFY才读V70场；不投影、不拟合相位/幅值、不改floor、不择优分母。原式未过的功率只作为diagnostic；没有候选则逐项NOT_RUN，不填零。失败候选也应完成合法恢复和诊断输出，以区分求解失败与后处理缺失。

历史P6/L5散射E/H约1.14449e-4/1.23013e-4、240点9.56042e-4的连续精度FAIL保持。即使本轮严格复现同一p5离散，也不授continuum convergence或原尺寸2TB/48h资格。[R10]

## 8. 单一时间合同、资源与连续排障

V75新总窗43200s（12h），从第一项实际工作记录同boot monotonic T0及UTC配对；最后3600s留收口。只有一个总截止，父子/嵌套计时是诊断子项，不重复扣费。**取消新批次4h H和6h I阶段硬门，不继承V74的used=max(used,elapsed)规则。** 保留上述10800s KSP、800作用和物理/资源门。12h是研发许可上限，不是成功承诺，也不能把48h生产目标当成可反复刷新研究预算。

H期间持续报已完成基础块、宏和下一阶段余量；没有进展需区分正常高CPU、IO、交互等待与死锁。进入PC numeric前，剩余有载时间必须覆盖：基于旧39因子实际记录并声明裕量的新numeric预测、10800s完整KSP上限、至少4500s完整恢复/输出/独立验算；实际尾段预测更大时取更大值。不能在尾段已明显放不下时启动重factor；也不能只因软预测超4h就提前结束健康准备。预测不是measured，含不确定性并只沿新证据更新，不无限滚动截止。

保持整树规划/警戒/采样停止96/112/128GiB，PC全部双倍symbolic总门80GiB。每个numeric前liveRSS+该阶段全部尚未分解且将共驻的双倍估计+future≤96GiB；future至少12GiB并列举Krylov、PC、审核/恢复工作区，已经live的对象不重复另加。H串行宏因子不虚构960份同时常驻，但lift、base、缓存和实际临时数组全部入账。未来主V/Z257向量4,841,028,816B只是derived载荷。[R4]

qualified native Linux/complex128/int64、MPI1/math1/CPU1/GPU0、ownswap/OOC0、宿主/cgroup/PSI与384GiB邻增长门、物理核/SMT隔离、heavy-lock和完整进程树watchdog维持；轻消费者沿原64/80/96GiB profile。禁止修改系统swap、邻任务、监督策略或忽略TERM。新ignored≤32GiB，Task上限696GiB，free≥50GiB并留512MiB证据余量。符号容量不够先做一次不改数学的生命周期/分块修正，不能直接扩大预算。

一个scope驱动case、aux、存储、future、supervisor和collector；在无FE的小fixture中实际走通新namespace，核对不是V51/V74 fallback，资格指针来自同源测试。普通工程错误同窗修复、targeted验收后从健康对象继续；同根因两次失败必须换正确等价实现或隔离，不能第三次盲重播长命令。ABI、材料、原式、系统性缓存不兼容或真实资源监督失败仍须停止受影响计算，保存能独立完成的结果。

## 9. 成本、目标路线与决策出口

必须分开：本批新增研发elapsed及不重叠命令下界；V74+V75累计研发费用；复用准备后的单场进程；一次必要完整准备加求解/恢复/输出的N=1成本；从几何开始的packet-only cold。881旧宏和父V70/V71准备不能免费，重复失败也不能冒充正常必要成本。每项注明measured/derived/predicted/unknown；没有数据就保留unknown。

| V75结果 | 决策 |
|---|---|
| 完整原式、严格场与资源通过 | 固定缩尺案例迭代资格；下一最小pilot为同案例去掉global-S构建历史的packet-only cold N=1，不立刻扩大物理尺寸 |
| E_H及全域见证通过，但完整FGMRES/场失败 | 形成这个固定harmonic+38RAS组合的真实负结果；不续原尾部或增加restart，下一机制需另审 |
| 精确资产或全域数学Gate失败 | 给具体包、行/端口、差值及可恢复范围；未跑KSP不称不收敛 |
| 仅普通工程错误或文档缺项 | 修复并消费健康对象，不能默认把全批交付降为组件面板 |

距最终目标仍有三类缺口：当前无合格可扩展迭代解；现有p/h连续精度未通过；真正cold准备和原尺寸的分布式trace/端口/粗层、全链RSS/48h尚未资格。批乘与检查点解决眼前时间浪费，不自动解决粗空间随电尺寸增长或全局粗LU复杂度。完整验证顺序仍是固定case求解→packet-only cold/精度资格→有实测校准的中间尺度及MPI数据所有权→目标尺寸。不能把828模式与小case容量直接线性外推到原尺寸external inventory。

邻分支本次只作范围核对：工程线@4e04f2fe2b3ea22e67cbd93ee1ffebfd66b50a79的Review V27要求保存数据独立生成完整q0 CSR；其最新实测仍是V26，不是已完成分解。Task42extra@e0508555ffec6d13fad68b7516971c5899a09901为神经特征坐标试验；dot@15713d3e09b63f65511c7b7f61fa043fdb23dca5本次未见ref更新。本报告不复制这些任务、不向邻支派活、不声称完整重审其全部源码。

## 10. 实现、入口与交付

commit顺序：C1持久化/兼容接入/单一预算及targeted tests；C2冻结入口和参数、clean后实际准备至迭代；必要C3只做已定位修复，活跃actor清场后再改受检HEAD；C4结果、response及两总账。每项沿原branch，不reset/stash/clean/amend/强推，不merge/master或邻worktree操作。已通过的旧高成本Gate不因文档变化重复。

以下是需新增的V75独立one-run入口，不声称当前已存在；全部经本任务资格化activation和监督，不直接执行旧closed V74 dat：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v75_harmonic_reuse_preflight.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v75_harmonic_coarse_complete.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v75_harmonic_trace_fgmres.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v75_compare_verify_cost.dat
```

PREFLIGHT只接入/资格，不藏PDE；COMPLETE允许声明的局部factor而不藏全域KSP；VERIFY不factor。实现先commit，相关compile/Ruff、targeted数学/缓存/计时/接口和四dat validate后连续执行；不先full pytest、重装环境、重新造参考或再做一轮大矩阵扫描。

交付response_v75.md、outcomes/durable_harmonic_completion_v75.md、summary/README、development_progress及development_model_registry短增量。紧凑records至少包括：reuse_compatibility、base_checkpoint_manifest、harmonic_completion、full_Galerkin_duality、factor_inventory、residual_history、complete_physics/paired_results、resource_costs_final、repair/source/run/closure，以及retained_iterative_contract_v75.json。复用原schema，仅补确有必要字段，不为文件数拆出大量平行账本。

主表必须回答：881旧宏究竟复用了多少、新numeric究竟多少、基础Galerkin新算/回读/失败重复分别多久、完整E_H是否通过、KSP实际步与原true、完整场资格、全过程峰/gap与necessary N=1成本。完整候选是主交付；若仍没有，必须给真实不可绕过的数学/资源/资产原因，不能只以“测试通过”替代。

正式run绑定input_original.dat、resolved_config.json、run_manifest.json、input_sha256.txt、physical_model_sha256.txt、source_sha.txt、run_summary.json、环境/MPI/资源和artifact hash。大数组ignored，Git只存轻量证据；保存完整失败。不把发布HEAD当数值source。最终只推送本分支，回读remote SHA/upstream/clean、closed/active null、后代清场与锁释放后暂停，不自动开V76。

```bash
git push origin HEAD:refs/heads/task42_neural_coarse_inverse
```

外部接口依据：[R11 NumPy matmul官方说明](https://numpy.org/doc/stable/reference/generated/numpy.matmul.html)、[R12 PETSc MatSetValues官方说明](https://petsc.org/release/manualpages/Mat/MatSetValues/)。它们只支持批乘/装配接口语义，不支持本案加速倍数或收敛结论。

本review提交前检查围栏、表格和内容身份；GitHub页面视觉渲染若无法实际查看则保持NOT_VERIFIED，不冒称通过。此项不授权绕过数值或资源Gate，也不要求为页面渲染重跑科学计算。
