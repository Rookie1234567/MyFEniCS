# Review V70：复用38块完成一次真实迭代，不让因子子预算代替求解结论

## 0. 裁决、目标与身份

**V71按pass_with_qualifications接受组件、资源否决及闭窗证据；完整迭代能力仍NOT_RUN，不授solver pass。批准V72_REUSE_38PATCH_FULL_ITERATIVE：复用已保存的38块、Z/E0和热算子，在同一0.7nm缩尺NOTCH上完成一次有界的numeric、RIGHT FGMRES及完整场验收。优先回答这套PC能否求解，再决定怎样压低它的成本。**

本轮要消除的blocker是：已有可承受的精确接口作用和数学合格的PC准备包，却尚无真实PC apply、收敛曲线和完整迭代场。它属于**求解器、内存准入与执行连续性**，不是新离散、NN训练或目标尺寸扩展。上轮64GiB因子子门挡住了74.8057GiB的双倍symbolic规划；这不是整机2TB容量失败。Codex遵守旧合同停止是正确的。本报告修正研究准入设计，不回写旧结果为PASS。

```text
repository             = Rookie1234567/MyFEniCS
execution_branch       = task42_neural_coarse_inverse
canonical_worktree     = /home/fenics/Projects/NN-Lab
review_date            = 2026-10-11 Asia/Singapore
reviewed_HEAD          = 7f7f9c0b2661e58b3eb75150e9e6275551cb393f
latest_commit_UTC      = 2026-10-11T02:33:36Z
latest_commit_local    = 2026-10-11 10:33:36 +08:00
latest_response        = response_v71.md
previous_review        = review_report_v69.md
previous_review_commit = 41ee5ea56e19de48bee71792cbcd7081ba6e755c
previous_review_blob   = 0705d5d2217894ae6d18254ab9ad2df1d36b4cd9
original_base          = ccd357885f7f9be84efe3be07868cc94f13d93fc
campaign               = V72_REUSE_38PATCH_FULL_ITERATIVE
required_response      = response_v72.md
ordinary_default       = UNCHANGED
NN_training            = NOT_AUTHORIZED
merge                  = NOT_APPROVED
```

最终目标仍为原50×25nm周期、z=-10..130nm、真空0.7nm、任意非可分三维材料/几何、complex128 Nédélec H(curl)、x/y Floquet、z Fourier-DtN、复E/H、全衍射和独立体吸收；单场必要构建、求解、恢复、输出与检查≤172800s。十进制2e12B是整机物理内存，须有系统余量、ownswap/OOC=0。本批s=7/135有限问题、MPI1和固定p5不是上述目标资格。

本合同明确覆盖V69的64GiB因子子门、仅允许消费通过旧容量门的PC_SETUP依赖和旧窗口关闭后的禁止重入；只建立独立V72窗口，不重开V71、不清零旧账、不改变原数值精度或整进程96/112/128GiB保护。重复收到本指令不得重复创建V72。

## 1. 最新事实与审阅范围

已访问当前分支、最近6个提交及文件差异，读取root/docs规则、仓库原则、task、最新review/response、summary和相关records，审查热作用消费者、局部/粗构造、numeric、retained FGMRES及准入源码。任务目录与增量中未发现新增独立补充任务书或同名V70。V69全文从会话原件读取，SHA256 c722b3200ce9c241108ef7874880a8579cc78b52107046cb8737f9f281bced83与远端blob一致。未SSH、未核验工作站此刻PID、未下载重算大型NPZ或运行新PDE。以下measured均为提交回执中的实测，本端复核其口径、原字段及代码链路。

依据：[V71回应](response_v71.md)、[汇总](outcomes/summary.md)、[独立数组审核](outcomes/records/scientific_checks_v71.json)、[PC库存](outcomes/records/bounded_pc_inventory_v71.json)、[最终费用](outcomes/records/resource_costs_final_v71.json)、[消费合同](outcomes/records/retained_iterative_contract_v71.json)、[闭窗](outcomes/records/closure_v71.json)。O/P/VERIFY实际source分别为d064028e4813e2f944a2b994e88f93c9a65f4806、ee13ea8419b2a6cb6f137d6d975135dfe1e510e5、a8d73e8b4bb45c0b37d65fa46c785121048150ab；文档HEAD不是数值source。

| 对象与数据身份 | V71结果 | 审阅判断 |
|---|---:|---|
| 同一有限问题 | 25576tet/p5/828；完整FE1943745，接口含端口1177293 | 全部767280内部系数仍可恢复 |
| 热作用FE/port最大误差，measured | 5.21846573209e-16 / 6.43620108577e-17 | 原1e-10门通过 |
| 非零内部及端口RHS原式见证，measured | 1.46526959602e-14 | 组件通过，不是新物理解 |
| 冷读、映射和边界聚合，measured | 71.8003688981s | 必须计入本次部署 |
| 三次热作用，measured | 1.22402047995 / 1.23098633904 / 1.31843893789s | 可用于实际迭代，不再开展热内核优化 |
| 局部块与稀疏粗层，measured inventory | 38块；31965–68680行；Z有23529162项；E0为7068行 | 数学准备与实际factor资格分开 |
| Galerkin全作用最大误差，measured | 1.49728602378e-15 | 原1e-10门通过 |
| 因子双倍symbolic，predicted | local79520000000B＋coarse802000000B | 总80322000000B＝74.8056918383GiB，不是实测RSS |
| V71子门，policy | 68719476736B＝64GiB | 超11602523264B，旧容量FAIL保留 |
| numeric / KSP / 新候选，measured count | 0 / 0 / 0 | 无不收敛或PC apply性能证据 |
| P全段 / 其中粗Galerkin，measured | 3392.80855081 / 2856.99820756s | 子计时包含于父区间，不相加 |
| 准备阶段采样树峰 / 最大gap，measured | 8.79606246948GiB / 1.60104868095s | 无numeric的峰，不是完整求解峰 |

V70第二次作用34.456206552s与本次热调用的历史耗时比约26.1–28.2；不是配平冷启动或整场加速比。V71总因子需求约99%来自局部块，不是7068行粗因子。继续重建粗层不能解决这次资源否决。

V70直接参照仍有效；P6/L5历史散射E/H约1.14449e-4/1.23013e-4、240点约9.56042e-4，仍超过1e-4门。同离散求解器资格可先检验，但不得因此授连续精度。

## 2. 冻结方程、数据和唯一候选

材料、载波、入射、mesh、MPC及全部828模式沿V71/V69冻结；physical SHA256为df26b8cf28e1115bdb2eb9ac9b79e698596133305310d26c1d664f94e2c5be44。仍为原κ、0.7nm、1000个NOTCH tetra、grazing1度/azimuth5度/s及完整Cκ。physical SHA现场按原schema重算；新增控制配置改变input/method SHA，不得悄悄改变physical身份。

物理弱式和全部有限元方向不变。接口计算只是把内部未知量局部解出，保留原方程的精确消元：

```math
S=A_{tt}-A_{ti}A_{ii}^{-1}A_{it},\qquad
b_t^{\mathrm{red}}=f_t-A_{ti}A_{ii}^{-1}f_i,\qquad
u_i=A_{ii}^{-1}(f_i-A_{it}u_t).
```

这里t包含接口与完整端口，i为单元内部；复数非Hermitian耦合不以共轭猜造。使用原数值坐标Ahat=L S R、bhat=L b_red，端口缩放恰好一次。沿V71的Z、E0=Z* Ahat Z和38块core/halo/唯一owner，不换p/h/M、不重分区、不改ordering/shift/吸收、无ILU扫描、无NN。先粗后局部的原PC保持：

```math
z_0=Z E_0^{-1}Z^*r,\qquad
M^{-1}r=z_0+B_{\mathrm{RAS}}(r-\widehat S z_0).
```

粗层负责跨区域协调，重叠局部块处理剩余误差；每次PC还调用一次原接口算子。其收敛性未知，旧低阶粗修正失败不被覆盖。FGMRES右预条件的适用性见[PETSc官方说明](https://petsc.org/release/manualpages/KSP/KSPFGMRES/)，不由此推断本PC一定有效。

只读父资产指针从retained_iterative_contract_v71.json及绑定的完整payload取得：V70 local_packet manifest SHA256为9bef5add6398999c70c21c7f26a86833fc1eb46f98598c8503aa3c41743728da；V71 P result SHA256为dea558cc24bbb908e41df166b0c86343161aa903c1bfa4c2347e1bb3c09b5176；独立VERIFY result SHA256为e0bb6611e18c9594e22ffba23e084bedc0bf14c9db5e6fd94f5a46144bd0bc09。不凭文件名猜路径。一次受控读取时校验schema、hash、dtype、CSR、owner和尺度，之后只读复用，不每次matvec重哈希。

生产V72禁止形成/读取global fine K/S或global fine factor；允许并记录父内部LU及新38个局部和1个粗LU。参考场只能在候选冻结后评分。此禁止的实测范围是prepared-start V72；父V70 BUILD同时形成过S，因此当前还不能宣称从几何开始的完整cold pipeline从未形成S。

## 3. 新准入：因子子预算80GiB，整进程保护不变

64GiB继续作为V71的原门和后续压缩目标，不作为本批同候选求解的先决条件。本批因子双倍symbolic总和许可为80GiB＝85899345920B；每块仍须原图、原ordering、成功且可靠的symbolic。当前80322000000B满足这个新子门，**但尚未取得numeric准入或证明实测内存安全**。

整进程仍是planning96GiB、warning112GiB、sampled stop128GiB，默认轻量阶段64/80/96GiB。不能借用旧256GiB，更不能借口整机2TB而占满它。96GiB减当前双倍symbolic还剩21.1943081617GiB容纳非因子对象；以V71准备峰加8GiB未来储备作说明性算术，总约91.60GiB。这不是V72实测，也不是正式准入，必须替换成实际对象共驻状态。

在numeric之前先建立并计量必要热包、Z、owner、原式evaluator等常驻对象，释放不再需要的准备容器；每次只读一个局部CSR，形成其PETSc矩阵，分解并留下该factor，及时释放该CSR/PETSc输入矩阵。不得同时装载全部38份CSR或再拼成全局S。每个factor前按下式重新准入：

```math
M_{\mathrm{plan},j}
=\mathrm{RSS}_{\mathrm{tree},j}
+\sum_{k\in\mathrm{not\ factored}}2e_k
+M_{\mathrm{future},j}
\le96\,\mathrm{GiB}.
```

未分解集合包含当前块；已形成factor在RSS内，不再把完整80GiB重复加到它上面。future在numeric阶段至少8GiB，须列出Krylov、额外retained/恢复/独立原式向量、PC及本块工作区，不能把8GiB当作不检查实际尺寸的万能余量。若逐项预测更大，以更大值为准。65条retained主向量1224384720B只是已有derived基数，不含所有工作区。始终预留完整后处理空间或先释放factor再进入后处理。

保留每因子ICNTL(23)=2×原可靠estimate_decimal_MB，ICNTL(22)=0。该控制限制的是MUMPS工作内存，并非Python/PETSc/整进程RSS的通用硬上限，见[PETSc MUMPS官方说明](https://petsc.org/release/manualpages/Mat/MATSOLVERMUMPS/)。记录实际INFOG、内存设置、numeric时间、进程树RSS和每步剩余预测；监督仍必须覆盖整个自身后代。预测或实测不合格时停止依赖工作，保留原因，不通过换单位、降安全倍数、隐藏factor或自动扩大整进程额度解决。

本批不执行V71提出的总预算驱动再二分：目前尚未测得原38块PC的效能，且已有整进程余量可进一步核验。若这个新共驻准入仍失败，只允许一次不改数学的生命周期去重并重新计算准入；仍失败则给出具体超额对象与需要释放的字节，保留健康资产，不转成无界分区研究。

## 4. 三个接续修复必须在真正迭代前完成

**读取资格与旧容量结论分离。** [bounded_trace_scope.py](../../src/solvers/bounded_trace_scope.py)把ITERATE依赖绑定到PC_SETUP.pass_gate；V71为false。新V72 REUSE_ADMIT须读取旧独立checker的mathematics_pass、原式/owner/Galerkin和真实库存，并生成自己的capacity及数学准入。不得把旧JSON改true、删除闭窗或假装V71当时已获准。

**不要求不存在的旧预测校准。** [bounded_trace_study.py](../../src/solvers/bounded_trace_study.py)只在旧P准入后生成local_forecast_calibration，而ITERATE无条件读取它。V71没有这个字段。新流程在同一ITERATE进程逐块numeric；第一个成功factor完成一个固定RHS三角解校准后保留，接着形成其余factor，不把它销毁后再建，不重跑P或粗Galerkin来补字段。每个实际factor至少一份固定非零RHS原块残差≤1e-8及finite见证；记录backend失败、真实数值不可解和实现错误的区别。

**异常恢复与释放真正可执行。** numeric结束后立即进入拥有PC的try/finally，再创建可能失败的evaluator/向量；所有异常须销毁已拥有factor并清场。run_retained_fgmres当前硬编码zero start；若沿用“实现错误后从合法retained续算”的合同，须先增加显式optional initial vector接口及定点测试，旧默认仍从零。续算只读本批最近合法scaled-retained和相同A/RHS/尺度；不得读V70参考解。累计调用、已耗迭代和时间不清零，明确新KSP实例与丢失的Krylov基，而不是冒称原KSP无缝延续。

只作新增消费、准入、缺校准、异常释放及初值协议的最小回归；已有热作用和Galerkin数学不变时不重跑全部资格。初次V72热包加载至多两次固定原作用配对，用已有见证，不新增优化campaign。大数组缺失时查已声明hash副本；无法找到则ASSET_BLOCKED，不为补文件重做数小时旧构建。

## 5. 必须消费真实PC并尝试完整FGMRES

REUSE_ADMIT通过后，连续完成39个numeric、真实PC见证和一次正式KSP.solve，不在代码commit、单元测试、symbolic或第一块成功后停等审阅。局部因子不可解不改为identity，不用全局细层LU补救。两个固定复向量的实际PC有限性及复齐次见证沿旧1e-10门；不把它称为收敛证明。所有local/coarse三角解、PC内部原作用和时间分别记录。

保持RIGHT FGMRES、restart32、max256、retained零初值；恢复含固定内部特解。累计迭代预算6h，最多600次全域作用（接口、PC内部、显式true和独立原式按类型分列），资格目标≤12次，接近590次时为最后保存与原式检查留出余额。V71已付8次另列，不抹去。普通进展不使用第16/32步必须降低若干倍的早筛选；无事前收敛证书不是不进入求解的理由。

每32步、第一次达到候选收敛及退出时保存retained，检查显式接口true及完整恢复原式；同一迭代不要因不同writer重复重算。保持retained true≤1e-11；独立true/native/augmented/port各≤1e-6；恢复/MPC/Schur-original等原恒等式各≤1e-10。独立direct1e-10仍单列，不能用它未经授权否决已通过的formal迭代门。不得以参考误差选停止点或追加求解。

在numeric前以剩余固定窗口、已测热作用和实际局部分解进度做观察性费用预测；缺少从未测过的完整PC时间应记unknown，不伪造0或要求旧throwaway校准。PC两次实测后更新预测。时间准入需给完整输出审核预留≥4500s，并至少能容纳一个完整restart及对应原式检查；预测“256步未必跑得完”本身不是禁止任何迭代的理由。最终服从6h/256/600及固定窗口的先到上限，不能因趋势继续自动扩窗。

到预算而未过门也须保存最终有限候选、true residual和原因，按diagnostic完成可用输出；非有限或身份失效的向量不得冒作合法场。新实现错误可在原窗口内作最小修复并从本批合法retained接续；数学停滞不当bug，不换PC/参数重开。

## 6. 全场、生命周期与成本验收

最终scaled-retained、物理trace、full/reduced RHS、left/right尺度、source及parent packet指针先原子保存。退出KSP，释放38个local＋1个coarse因子及无用缓存，记录RSS变化，再做完整恢复/六场/功率。必须区分“对象已销毁”和“RSS实际下降”，不以gc调用次数代替证据。

冻结候选后才读V70场，保持同基系数先相减的完整比较和原分母/floor：六场、240点及物理参考面复通道差≤1e-6；R/T/A/A_volume差≤1e-8；逐mode功率差≤1e-9；独立能量闭合≤1e-5。全部828模式、所有内部自由度和total/scattered复E/H/curl保留，不删弱通道、不拟合幅相。official仅授原式通过的结果；方程通过、严格同离散再现、连续精度分别裁决。

writer、JSON、checker或文档故障只补消费已保存状态；保留原失败，不重新numeric/KSP来生成相同场。无合格场时不能沿用V70的R/T/A填写V72。若原式通过但场比较未过，保留这个有价值但不充分的结果，不降低门限。

费用分三本账：V72 prepared-start从实际必要读取到完整输出/验收；从几何开始的cold候选成本（仍有未测packet-only构建，不授完整cold速度比）；全部历史研发及参考计算的已付成本。父V70 BUILD9646.82648389s、V71 O/P和旧直接参考不免费，也不在不同嵌套计时中重复相加。当前历史已知下界来自最终resource_costs，不从旧plan覆盖它。与V70 prepared SOLVE12666.5476045s、111.277801514GiB只作口径明确的历史观察；未配平不授生产速度/内存收益。

## 7. 范围、预算、入口与交付

独立V72固定总窗14h，自首次实际实施/读取开始，科学有载≤12h，末1h用于收尾；numeric及PC资格上限3h、正式迭代上限6h，完整输出审核预留≥4500s。它们是研究资源上限，不是预计耗时。实现、读取、等待、失败、续算和IO均计费。普通修复重放累计≤2.5h；同根因两次无效后改用已授权的正确路径或隔离该依赖，不能第三次盲跑、反复开卡。visual未取得记NOT_VERIFIED，不以文档渲染问题重跑科学计算。

保持原ABI/complex128/int64、MPI1、math/CPU1、GPU/Loader0、ownswap/OOC0；宿主/cgroup/PSI、384GiB邻增长余量、物理核/SMT隔离、机器heavy锁和进程检查沿当前已授权保护。一次一个heavy；无法确认可用资源时只做允许的轻量接线，不启动actor、不改邻任务/系统配置。新ignored≤32GiB、Task去重≤632GiB、free≥50GiB并留512MiB证据余量，父资产只读不复制、不删除负结果腾空间。

正式新入口只需三个，须创建并validate，一个dat只表示一项明确工作：

```bash
python scripts/run_case.py input/task042_neural_coarse_inverse/v72_reuse_admit.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v72_trace_fgmres_solve.dat
python scripts/run_case.py input/task042_neural_coarse_inverse/v72_compare_verify_cost.dat
```

REUSE_ADMIT核对健康资产/数学/预算，不重建38块/Z/E0，不numeric；ITERATE在同一进程完成numeric、真实PC、唯一正式求解及恢复；VERIFY消费冻结候选、不新增PDE/factor。复用现有通用数值模块和薄runner，通过显式新scope/参数实现，V71历史入口默认不变；不复制另一套求解器，不full pytest/CI或全仓索引。

提交计划：C1新消费与资源/恢复协议、定点测试；C2必要的确定实现修复（有则单独提交并保留source）；C3实际结果和紧凑交付。每次数值运行前clean源码已提交，记录原dat、resolved_config、manifest、input/physical/source SHA、环境、MPI/资源和artifact hash。不得以最终文档HEAD冒充运行source。

交付response_v72.md、outcomes/reused_trace_iterative_v72.md与紧凑records：reuse_admission、逐factor容量/残差/时间、PC实测、完整residual history与分类计数、retained/全场/828通道、独立checker、费用/实际采样gap/生命周期、修复和未运行原因、retained_iterative_contract_v72.json。README/summary/两总账短追加，不复制旧数万行payload。主结论必须回答：有没有进入KSP、能否再现同离散场、具体卡在什么数值或资源项，而不是只报测试数量。

只在canonical本分支fetch/ff-only、提交并push：git push origin HEAD:refs/heads/task42_neural_coarse_inverse。先检查branch/HEAD/upstream/origin/worktree/活跃actor；不reset/stash/clean/amend/强推，不改旧task/review/response。核对远程完整SHA、clean、closed/active null、后代清场与锁释放后交付暂停，不merge、不自动开新批次。

## 8. 对最终目标的下一步判定

若本批完整同离散PASS，应先形成包含真正实测factor/PC/原式/输出的成本模型，再设计packet-only cold构建和受容量约束的中间尺度/MPI pilot；不能直接跳到最大0.7nm原尺寸。若失败，用最终true残差曲线及local/coarse/原作用费用决定下一项具体改进，不能重新无界扫描p2/p3/p4或ILU。局部因子的总量仍随子域数量增长，未来还须控制单块规模、并行所有权、端口存储和粗问题规模。

当前把全部828端口放进7068行粗问题只是有限case做法；目标external inventory增长时不得突破8192行并声称同一有界粗层，须另做分布式端口/粗空间设计。原尺寸准确性、历史空间增量FAIL和48h完整cold成本仍是独立blocker。

邻线只读核对：task40extra_0p7nm_engineering@4a524251339e00ad481b29af61df4f4625ed2581已提交Review V25，推进完整原尺寸体积作用及selected-q消费者，不是完整场已通过；本支不抢做其工程任务。task42extra_feinn_5nm、NN-V3和dot保持独立，不跨worktree派活、不训练NN、不移植邻支大包。

**2TB显著放宽预算，但目标主线仍须从全局直接分解和显式大耦合矩阵走向分布式、matrix-free和可扩展Full3D iterative；Hybrid只作适用结构的并行加速路线。本轮的最小实质交付，是终于测到这套已准备好的PC对应的完整求解过程，而不是再准备一套尚未运行的PC。**
